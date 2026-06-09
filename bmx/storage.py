from whitenoise.storage import CompressedManifestStaticFilesStorage


class RobustManifestStorage(CompressedManifestStaticFilesStorage):
    # Při chybějícím manifestu (před prvním collectstatic) vrátí původní název
    # souboru místo vyhození ValueError. Po spuštění collectstatic se automaticky
    # přepne na hašovaná jména.
    manifest_strict = False
