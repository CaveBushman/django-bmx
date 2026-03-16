from django.apps import AppConfig


class ThemeConfig(AppConfig):
    name = 'theme'

    def ready(self):
        # Jazzmin's paginator tag calls format_html() without arguments,
        # which crashes on Django 6. Override it with a safe implementation.
        try:
            from django.contrib.admin.views.main import PAGE_VAR
            from django.utils.safestring import mark_safe
            from jazzmin.templatetags import jazzmin as jazzmin_tags

            def safe_jazzmin_paginator_number(change_list, i):
                html_str = ""
                is_start = i == 1
                is_end = i == change_list.paginator.num_pages
                spacer = i in (".", "…")
                current_page = i == change_list.page_num

                if is_start:
                    link = (
                        change_list.get_query_string({PAGE_VAR: change_list.page_num - 1})
                        if change_list.page_num > 1
                        else "#"
                    )
                    html_str += """
                    <li class="page-item previous {disabled}">
                        <a class="page-link" href="{link}" data-dt-idx="0" tabindex="0">«</a>
                    </li>
                    """.format(link=link, disabled="disabled" if link == "#" else "")

                if current_page:
                    html_str += """
                    <li class="page-item active">
                        <a class="page-link" href="javascript:void(0);" data-dt-idx="3" tabindex="0">{num}</a>
                    </li>
                    """.format(num=i)
                elif spacer:
                    html_str += """
                    <li class="page-item">
                        <a class="page-link" href="javascript:void(0);" data-dt-idx="3" tabindex="0">…</a>
                    </li>
                    """
                else:
                    query_string = change_list.get_query_string({PAGE_VAR: i})
                    end_class = "end" if is_end else ""
                    html_str += """
                        <li class="page-item">
                        <a href="{query_string}" class="page-link {end}" data-dt-idx="3" tabindex="0">{num}</a>
                        </li>
                    """.format(num=i, query_string=query_string, end=end_class)

                if is_end:
                    link = (
                        change_list.get_query_string({PAGE_VAR: change_list.page_num + 1})
                        if change_list.page_num < i
                        else "#"
                    )
                    html_str += """
                    <li class="page-item next {disabled}">
                        <a class="page-link" href="{link}" data-dt-idx="7" tabindex="0">»</a>
                    </li>
                    """.format(link=link, disabled="disabled" if link == "#" else "")

                return mark_safe(html_str)

            jazzmin_tags.jazzmin_paginator_number = safe_jazzmin_paginator_number
        except Exception:
            pass
