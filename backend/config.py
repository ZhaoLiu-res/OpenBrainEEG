from pydantic import BaseModel, Field

class FilterConfig(BaseModel):
    l_freq: float = 0.5
    h_freq: float = 40.0
    notch_freq: float = 50.0
    notch_harmonics: int = 3


class BadChannelConfig(BaseModel):
    method: str = "pyprep"
    threshold_std: float = 3.0


class ReferenceConfig(BaseModel):
    method: str = "average"


class ASRConfig(BaseModel):
    enabled: bool = True
    cutoff: float = 20.0


class ICAConfig(BaseModel):
    enabled: bool = True
    method: str = "fastica"
    n_components: int | None = None
    ic_reject_threshold: float = 0.8
    manual_exclude: list[int] | None = None
    reject_categories: list[str] = [
        "eye blink",
        "muscle artifact",
        "heart beat",
        "line noise",
        "channel noise",
        "other",
    ]


class EpochConfig(BaseModel):
    enabled: bool = False
    duration: float = 2.0
    overlap: float = 0.0
    autoreject: bool = True


class InputAdapterConfig(BaseModel):
    source_format: str = "auto"
    signal_unit: str = "uV"
    exg_channel_count: int | None = None
    channel_names: list[str] = Field(default_factory=list)
    montage_name: str | None = None


class PipelineConfig(BaseModel):
    """清洗流水线完整配置。"""

    preset_code: str = "custom"
    preset_name: str | None = None
    report_language: str = "zh"
    filter: FilterConfig = Field(default_factory=FilterConfig)
    bad_channel: BadChannelConfig = Field(default_factory=BadChannelConfig)
    reference: ReferenceConfig = Field(default_factory=ReferenceConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    ica: ICAConfig = Field(default_factory=ICAConfig)
    epoch: EpochConfig = Field(default_factory=EpochConfig)
    input_adapter: InputAdapterConfig = Field(default_factory=InputAdapterConfig)

    export_formats: list[str] = Field(default_factory=lambda: ["fif", "edf", "csv"])
    generate_report: bool = True
    report_formats: list[str] = Field(default_factory=lambda: ["html", "pdf"])
