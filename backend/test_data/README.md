# EEG examples / 脑电样例

Included, unchanged from PhysioNet EEG Motor Movement/Imagery Dataset v1.0.0:

| File | Description | Data |
| --- | --- | --- |
| physionet/S001R01.edf | Eyes-open baseline / 睁眼静息 | 64 channels, 160 Hz, 61 s |
| physionet/S001R04.edf | Left/right hand motor imagery / 左右手运动想象 | 64 channels, 160 Hz, 125 s |

Source: https://physionet.org/content/eegmmidb/1.0.0/
License: [ODC-By 1.0](https://opendatacommons.org/licenses/by/1-0/), see LICENSE-DATA.txt.
SHA256 values and direct source URLs are in manifest.json, checked against the
upstream SHA256SUMS.txt before inclusion. These are public research recordings,
not data collected by OpenBrainEEG or Brainifly.

Please cite / 请引用：
- Schalk, G. (2009). EEG Motor Movement/Imagery Dataset (version 1.0.0). PhysioNet. https://doi.org/10.13026/C28G6P
- Schalk G., McFarland D.J., Hinterberger T., Birbaumer N., Wolpaw J.R. (2004). BCI2000: A General-Purpose Brain-Computer Interface (BCI) System. IEEE Transactions on Biomedical Engineering 51(6):1034–1043.
- Pollard T. et al. (2026). PhysioNet as a global platform for biomedical research. Nature Health. https://doi.org/10.1038/s44360-026-00096-z

Optional GDF: The UI also recognizes bci_competition/A01T.gdf. It is deliberately
not included: redistribution terms have not been confirmed. Obtain data directly
from https://www.bbci.de/competition/iv/ under its terms, then place the file at
that path for personal testing. Its absence does not affect the two EDF examples.

运行 python start.py sample 可重新获取/校验基线 EDF；两个 EDF 随仓库提供。
不要提交个人、临床或未确认再分发条款的数据。
