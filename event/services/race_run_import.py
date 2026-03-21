import logging
import os
import re

import lxml.html

from django.conf import settings
from django.db import transaction

from event.models import Event, RaceRun, Result
from rider.models import Rider
from rider.plates import normalize_plate_value


logger = logging.getLogger(__name__)


ROUND_TYPE_BY_UPLOAD_KEY = {
    "motos": "MOTO",
    "motos_results": "MOTO",
    "1_16": "F16",
    "1_16_results": "F16",
    "1_8": "F8",
    "1_8_results": "F8",
    "1_4": "F4",
    "1_4_results": "F4",
    "1_2": "F2",
    "1_2_results": "F2",
    "final": "FINAL",
    "final_results": "FINAL",
}

RESULT_KEYS = {"motos_results", "1_16_results", "1_8_results", "1_4_results", "1_2_results", "final_results"}
START_KEYS = {"motos", "1_16", "1_8", "1_4", "1_2", "final"}


def _normalize_text(value):
    return " ".join((value or "").strip().split())


def _normalize_category(value):
    return _normalize_text(value)


def _normalize_name(value):
    cleaned = re.sub(r"\[[^\]]*\]", "", value or "")
    return _normalize_text(cleaned).upper()


def _normalize_place(value):
    return _normalize_text(value)


def _parse_place_token(value):
    match = re.match(r"\s*((?:\d+(?:st|nd|rd|th))|DNS|DNF|DSQ|REL|NP)", str(value or ""), re.IGNORECASE)
    if not match:
        return ""
    return _normalize_place(match.group(1))


def _parse_int(value):
    if value in (None, ""):
        return None
    match = re.search(r"-?\d+", str(value))
    return int(match.group(0)) if match else None


def _parse_qualified_marker(value):
    return "*" in str(value or "")


def _parse_lane(value):
    return _parse_int(value)


def _parse_heat_lane(value):
    match = re.match(r"\s*([^/]+?)\s*/\s*(\d+)\s*$", str(value or ""))
    if not match:
        return None, None
    return _normalize_text(match.group(1)), int(match.group(2))


def _parse_time_triplet(value):
    raw_value = value or ""
    brace_match = re.search(r"\{\s*(\d+[.,]\d+)\s*\}", raw_value)
    hill_from_braces = None
    if brace_match:
        hill_from_braces = float(brace_match.group(1).replace(",", "."))

    value_without_braces = re.sub(r"\{[^}]*\}", " ", raw_value)
    floats = [
        float(number.replace(",", "."))
        for number in re.findall(r"\d+[.,]\d+", value_without_braces)
    ]

    if hill_from_braces is not None and len(floats) == 1:
        return hill_from_braces, None, floats[0]

    if len(floats) >= 3:
        return floats[0], floats[1], floats[2]
    if len(floats) == 2:
        return floats[0], None, floats[1]
    if len(floats) == 1:
        if hill_from_braces is not None:
            return hill_from_braces, None, floats[0]
        return None, None, floats[0]
    if hill_from_braces is not None:
        return hill_from_braces, None, None
    return None, None, None


def _table_category(caption_text):
    match = re.match(r"\s*(.*?)\s*\(\d+\s+Riders?\)\s*$", caption_text or "", re.IGNORECASE)
    return _normalize_category(match.group(1) if match else caption_text)


def _is_beginner_category(category):
    return _normalize_category(category).lower().startswith("beginners")


def _is_20_category(category):
    lowered = _normalize_category(category).lower()
    if "cruiser" in lowered or lowered.startswith("cr "):
        return False
    return True


def _extract_tables(path):
    with open(path, encoding="utf-8") as handle:
        document = lxml.html.fromstring(handle.read())

    tables = []
    for table in document.xpath("//table"):
        caption = table.xpath("./caption")
        category = _table_category(caption[0].text_content() if caption else "")
        headers = [
            _normalize_text(cell.text_content())
            for cell in table.xpath("./tr[1]/th")
        ]
        rows = []
        for row in table.xpath("./tr[position()>1]"):
            cells = row.xpath("./td")
            if not cells:
                continue
            cell_items = []
            for cell in cells:
                text = _normalize_text(cell.text_content())
                html = lxml.html.tostring(cell, encoding="unicode")
                cell_items.append({"text": text, "html": html})
            rows.append(cell_items)
        tables.append({"category": category, "headers": headers, "rows": rows})
    return tables


class RaceRunImportService:
    def import_event_runs(self, event):
        if isinstance(event, int):
            event = Event.objects.get(pk=event)

        stats_dir = os.path.join(settings.MEDIA_ROOT, "event_stats", str(event.pk))
        if not os.path.isdir(stats_dir):
            RaceRun.objects.filter(event=event).delete()
            return 0

        entity_index = self._build_entity_index(event)
        records = {}

        for filename in sorted(os.listdir(stats_dir)):
            file_path = os.path.join(stats_dir, filename)
            if not os.path.isfile(file_path) or not filename.lower().endswith(".html"):
                continue
            upload_key = filename.split("__", 1)[0]
            if upload_key in START_KEYS:
                self._consume_start_file(file_path, upload_key, entity_index, records)
            elif upload_key in RESULT_KEYS:
                self._consume_result_file(file_path, upload_key, entity_index, records)

        with transaction.atomic():
            RaceRun.objects.filter(event=event).delete()
            created = 0
            for record in records.values():
                RaceRun.objects.create(
                    result=record.get("result"),
                    event=event,
                    rider=record.get("rider"),
                    category=record["category"],
                    is_beginner=record.get("is_beginner", False),
                    is_20=record.get("is_20"),
                    round_type=record["round_type"],
                    round_number=record["round_number"],
                    heat_code=record["heat_code"],
                    plate=record["plate"],
                    gate=record.get("gate"),
                    lane=record.get("lane"),
                    place=record.get("place"),
                    race_points=record.get("race_points"),
                    moto_points=record.get("moto_points"),
                    qualified_to_next_round=record.get("qualified_to_next_round"),
                    hill_time=record.get("hill_time"),
                    finish_time=record.get("finish_time"),
                    split_1=record.get("split_1"),
                )
                created += 1

        return created

    def _build_entity_index(self, event):
        results = Result.objects.filter(event=event).select_related("rider")
        plate_index = {}
        name_index = {}
        for result in results:
            category = _normalize_category(result.category)
            rider = result.rider
            plate = normalize_plate_value(
                getattr(rider, "plate_text", "") or getattr(rider, "plate", "")
            )
            full_name = _normalize_name(f"{result.first_name or ''} {result.last_name or ''}")

            if plate:
                plate_index[(category, plate)] = {"result": result, "rider": rider}
            if full_name:
                name_index[(category, full_name)] = {"result": result, "rider": rider}

        riders = Rider.objects.all()
        for rider in riders:
            plate = normalize_plate_value(
                getattr(rider, "plate_text", "") or getattr(rider, "plate", "")
            )
            full_name = _normalize_name(f"{getattr(rider, 'first_name', '')} {getattr(rider, 'last_name', '')}")
            payload = {"result": None, "rider": rider}
            if plate:
                plate_index.setdefault(("", plate), payload)
            if full_name:
                name_index.setdefault(("", full_name), payload)
        return {"plate": plate_index, "name": name_index}

    def _match_entities(self, entity_index, category, plate, full_name):
        key_by_plate = (_normalize_category(category), normalize_plate_value(plate))
        payload = entity_index["plate"].get(key_by_plate)
        if payload:
            return payload
        key_by_name = (_normalize_category(category), _normalize_name(full_name))
        payload = entity_index["name"].get(key_by_name)
        if payload:
            return payload
        fallback_plate = ("", normalize_plate_value(plate))
        payload = entity_index["plate"].get(fallback_plate)
        if payload:
            return payload
        fallback_name = ("", _normalize_name(full_name))
        return entity_index["name"].get(fallback_name)

    def _run_key(self, rider, plate, round_type, round_number, heat_code):
        return (
            rider.pk if rider else None,
            normalize_plate_value(plate),
            round_type,
            round_number,
            _normalize_text(heat_code or ""),
        )

    def _ensure_record(self, records, result, rider, category, round_type, round_number, heat_code, plate):
        key = self._run_key(rider, plate, round_type, round_number, heat_code)
        records.setdefault(
            key,
            {
                "result": result,
                "rider": rider,
                "category": category,
                "is_beginner": _is_beginner_category(category),
                "is_20": _is_20_category(category),
                "round_type": round_type,
                "round_number": round_number,
                "heat_code": _normalize_text(heat_code or ""),
                "plate": normalize_plate_value(plate),
            },
        )
        return records[key]

    def _consume_start_file(self, path, upload_key, entity_index, records):
        round_type = ROUND_TYPE_BY_UPLOAD_KEY[upload_key]
        for table in _extract_tables(path):
            category = table["category"]
            headers = table["headers"]
            if round_type == "MOTO":
                moto_columns = [
                    (index, _parse_int(header))
                    for index, header in enumerate(headers)
                    if header.lower().startswith("moto ")
                ]
                for row in table["rows"]:
                    plate = row[0]["text"]
                    full_name = row[2]["text"]
                    payload = self._match_entities(entity_index, category, plate, full_name)
                    if not payload:
                        logger.warning("RaceRun import: chybí Rider/Result pro %s / %s / %s", category, plate, full_name)
                        continue
                    for column_index, moto_number in moto_columns:
                        heat_code, lane = _parse_heat_lane(row[column_index]["text"])
                        if not moto_number or not heat_code:
                            continue
                        record = self._ensure_record(
                            records,
                            payload.get("result"),
                            payload.get("rider"),
                            category,
                            round_type,
                            moto_number,
                            heat_code,
                            plate,
                        )
                        record["lane"] = lane
                continue

            for row in table["rows"]:
                plate = row[2]["text"]
                full_name = row[3]["text"]
                payload = self._match_entities(entity_index, category, plate, full_name)
                if not payload:
                    logger.warning("RaceRun import: chybí Rider/Result pro %s / %s / %s", category, plate, full_name)
                    continue
                heat_code = row[0]["text"]
                lane = _parse_lane(row[1]["text"])
                record = self._ensure_record(
                    records,
                    payload.get("result"),
                    payload.get("rider"),
                    category,
                    round_type,
                    None,
                    heat_code,
                    plate,
                )
                record["lane"] = lane

    def _consume_result_file(self, path, upload_key, entity_index, records):
        round_type = ROUND_TYPE_BY_UPLOAD_KEY[upload_key]
        for table in _extract_tables(path):
            category = table["category"]
            headers = table["headers"]
            if round_type == "MOTO":
                moto_columns = [
                    (index, _parse_int(header))
                    for index, header in enumerate(headers)
                    if header.lower().startswith("moto ")
                ]
                for row in table["rows"]:
                    qualified_to_next_round = _parse_qualified_marker(row[0]["text"]) if row else False
                    plate = row[1]["text"]
                    full_name = row[3]["text"]
                    payload = self._match_entities(entity_index, category, plate, full_name)
                    if not payload:
                        logger.warning("RaceRun import: chybí Rider/Result pro %s / %s / %s", category, plate, full_name)
                        continue
                    total_moto_points = _parse_int(row[4]["text"])
                    for column_index, moto_number in moto_columns:
                        cell_text = row[column_index]["text"]
                        place = _parse_place_token(cell_text)
                        if not moto_number or not place:
                            continue
                        rider = payload.get("rider")
                        key_prefix = (rider.pk if rider else None, normalize_plate_value(plate), round_type, moto_number)
                        matching_key = next(
                            (key for key in records if key[:4] == key_prefix),
                            None,
                        )
                        if matching_key:
                            record = records[matching_key]
                        else:
                            record = self._ensure_record(
                                records,
                                payload.get("result"),
                                payload.get("rider"),
                                category,
                                round_type,
                                moto_number,
                                f"MOTO {moto_number}",
                                plate,
                            )
                        record["qualified_to_next_round"] = qualified_to_next_round
                        hill_time, split_1, finish_time = _parse_time_triplet(cell_text)
                        record["place"] = place
                        record["moto_points"] = total_moto_points
                        if hill_time is not None:
                            record["hill_time"] = hill_time
                        if split_1 is not None:
                            record["split_1"] = split_1
                        if finish_time is not None:
                            record["finish_time"] = finish_time
                continue

            for row in table["rows"]:
                plate = row[1]["text"]
                full_name = row[3]["text"]
                payload = self._match_entities(entity_index, category, plate, full_name)
                if not payload:
                    logger.warning("RaceRun import: chybí Rider/Result pro %s / %s / %s", category, plate, full_name)
                    continue
                heat_code = headers[5] if len(headers) > 5 else round_type
                record = self._ensure_record(
                    records,
                    payload.get("result"),
                    payload.get("rider"),
                    category,
                    round_type,
                    None,
                    heat_code,
                    plate,
                )
                place = row[5]["text"] if len(row) > 5 else ""
                hill_time, split_1, finish_time = _parse_time_triplet(row[5]["text"] if len(row) > 5 else "")
                record["place"] = _parse_place_token(place)
                if hill_time is not None:
                    record["hill_time"] = hill_time
                if split_1 is not None:
                    record["split_1"] = split_1
                if finish_time is not None:
                    record["finish_time"] = finish_time
