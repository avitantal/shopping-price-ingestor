from dataclasses import dataclass

USER_AGENT = "ShoppingListApp/1.0 (avitantal@gmail.com)"
FTP_HOST = "url.retail.publishedprices.co.il"
SHUFERSAL_BASE_URL = "https://prices.shufersal.co.il"


@dataclass(frozen=True)
class ChainConfig:
    chain_code: str   # matches shopping.chains.code in DB
    gs1_id: str       # GS1 company prefix — used to match XML file names
    access_type: str  # "https_shufersal" | "ftp"
    ftp_user: str | None  # None for Shufersal (HTTPS only)


CHAINS: dict[str, ChainConfig] = {
    "shufersal": ChainConfig(
        chain_code="shufersal",
        gs1_id="7290027600007",
        access_type="https_shufersal",
        ftp_user=None,
    ),
    "mega": ChainConfig(
        chain_code="mega",
        gs1_id="7290055700014",
        access_type="ftp",
        ftp_user="Mega",
    ),
    "rami_levy": ChainConfig(
        chain_code="rami_levy",
        gs1_id="7290058140886",
        access_type="ftp",
        ftp_user="RamiLevi",
    ),
    "victory": ChainConfig(
        chain_code="victory",
        gs1_id="7290696200003",
        access_type="ftp",
        ftp_user="Victory",
    ),
    "osher_ad": ChainConfig(
        chain_code="osher_ad",
        gs1_id="7290103152017",
        access_type="ftp",
        ftp_user="osherad",
    ),
    "hazi_hinam": ChainConfig(
        chain_code="hazi_hinam",
        gs1_id="7290700100008",
        access_type="ftp",
        ftp_user="HaziHinam",
    ),
    "yohananof": ChainConfig(
        chain_code="yohananof",
        gs1_id="7290803800003",
        access_type="ftp",
        ftp_user="yohananof",
    ),
}
