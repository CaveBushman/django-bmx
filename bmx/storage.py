from whitenoise.storage import CompressedManifestStaticFilesStorage


class RobustManifestStorage(CompressedManifestStaticFilesStorage):
    # Vrátí původní název souboru místo ValueError když manifest chybí nebo
    # soubor v něm není (např. před prvním collectstatic).
    manifest_strict = False

    def url_converter(self, name, hashed_files, template=None):
        # WhiteNoise prochází JS/CSS a přepisuje URL reference na hašované verze.
        # Pokud odkazovaný soubor neexistuje (typicky *.map source mapy třetích
        # stran), vrátíme původní URL místo vyhození MissingFileError.
        converter = super().url_converter(name, hashed_files, template)

        def robust_converter(matchobj):
            try:
                return converter(matchobj)
            except Exception:
                return matchobj.group()

        return robust_converter
