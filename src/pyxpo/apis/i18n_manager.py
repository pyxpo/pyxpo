class I18nManager:
    """Layout direction flags (LTR only for now)."""
    isRTL = False
    doLeftAndRightSwapInRTL = True

    @staticmethod
    def allowRTL(allow: bool) -> None:
        return None

    @staticmethod
    def forceRTL(force: bool) -> None:
        return None

    @staticmethod
    def swapLeftAndRightInRTL(flip: bool) -> None:
        return None

    getConstants = staticmethod(lambda: {"isRTL": False, "doLeftAndRightSwapInRTL": True, "localeIdentifier": "en_US"})
