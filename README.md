# Huggingface Downloadhelper

A utility tool to simplify downloading models from Hugging Face.

## Features

- Easy download of models from Hugging Face Hub
- Progress tracking during downloads
- Resume interrupted downloads
- Authentication support for gated models

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/Huggingface-Downloadhelper.git
cd Huggingface-Downloadhelper

# Install dependencies
pip install -r requirements.txt
```

## Usage

```python
from downloadhelper import HuggingfaceDownloader

# Initialize the downloader
downloader = HuggingfaceDownloader(
    save_path="./models",
    use_auth=True  # Set to True if you need to download gated models
)

# Download a model
downloader.download("meta-llama/Llama-2-7b")
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
