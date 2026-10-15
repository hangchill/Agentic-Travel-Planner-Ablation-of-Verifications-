
## Download and install the official ChinaTravel sandbox.
## Run once after installing requirements.txt.

from pathlib import Path
from zipfile import ZipFile

from huggingface_hub import hf_hub_download

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_DIR = PROJECT_ROOT / "chinatravel" / "environment"

REPO_ID = "LAMDA-NeSy/ChinaTravel-Sandbox"


def install_sandbox(language, archive_name, folder_name):
    ## Check whether the sandbox is already installed.
    destination = ENV_DIR / folder_name

    if destination.exists() and any(destination.rglob("*.csv")):
        print(f"{folder_name}: already installed")
        return

    print(f"Downloading {language} sandbox...")

    ## Download the official archive from Hugging Face.
    archive_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=f"raw/{archive_name}",
        repo_type="dataset",
    )

    ## Extract the database into chinatravel/environment/.
    with ZipFile(archive_path) as archive:
        archive.extractall(ENV_DIR)

    print(f"{folder_name}: installed successfully")


if __name__ == "__main__":
    install_sandbox(
        "Chinese",
        "ChinaTravel_sandbox_zh.zip",
        "database",
    )

    print("\nSandbox setup complete!")
