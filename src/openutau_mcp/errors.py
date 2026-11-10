class OpenUtauError(Exception):
    """Error with a bilingual (English / Japanese) message."""

    def __init__(self, en: str, ja: str):
        super().__init__(f"{en} / {ja}")
