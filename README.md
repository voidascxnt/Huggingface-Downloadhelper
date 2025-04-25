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

### Basic Usage - Running the Batch File

The simplest way to use this tool is by running the batch file:

```bash
# Super Basic usge:
doubleclick the downloadhelper.bat

# Basic usage
downloadhelper.bat model_name

# Example: Download Llama-2-7b
downloadhelper.bat meta-llama/Llama-2-7b
```

### Command Line Options

```bash
# Specify a custom save directory
downloadhelper.bat meta-llama/Llama-2-7b --save-path="D:\my_models"

# Download a specific revision/branch
downloadhelper.bat meta-llama/Llama-2-7b --revision=main

# Download specific files only
downloadhelper.bat meta-llama/Llama-2-7b --files="pytorch_model.bin,config.json"

# Resume an interrupted download
downloadhelper.bat meta-llama/Llama-2-7b --resume

# Download without using authentication
downloadhelper.bat facebook/opt-350m --no-auth
```

### Authentication for Gated Models

To download gated models (like Llama-2), you need to set up authentication:

1. Create a Hugging Face account at https://huggingface.co
2. Create a token at https://huggingface.co/settings/tokens
3. Save your token (either as environment variable or when prompted)

```bash
# The tool will prompt for token if needed
downloadhelper.bat meta-llama/Llama-2-7b

# Or set it as an environment variable before running
set HF_TOKEN=your_token_here
downloadhelper.bat meta-llama/Llama-2-7b
```

### Advanced Python Usage

For those who want to use the underlying Python module directly:

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

### Error Handling

```python
try:
    downloader.download("meta-llama/Llama-2-7b")
except AuthenticationError:
    print("Authentication failed. Check your token.")
except ModelNotFoundError:
    print("Model not found. Check the model name and your access permissions.")
except DownloadError as e:
    print(f"Download failed: {e}")
```

### Parallel Downloads

```python
# Download multiple models in parallel
models = ["meta-llama/Llama-2-7b", "facebook/opt-350m"]
downloader.download_multiple(models, max_workers=2)
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
