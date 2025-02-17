# Generates Next Word Predictions Based On Trained Language Models

## Directory Structure
```
2024201043_assignment2
├── generator.py
├── README.md
└── Report.pdf
```

## To Run `generator.py`
```
python3 generator.py <lm_type> <corpus_path> <k>
```

### Supported `lm_type` Options:
- `-f` : FFNN Language Model
- `-r` : RNN Language Model
- `-l` : LSTM Language Model

## Pretrained Model Files
Download the pretrained `.pt` files from the following links:

- [Ulysses](https://drive.google.com/drive/folders/1NZzlmK-QWMLMXsro1XCm6QXbY0EhX930?usp=sharing)
- [Pride & Prejudice](https://drive.google.com/drive/folders/1lCracqoulDcjuF9qikS4aF1uR5vDIqyv?usp=sharing)

## Instructions
1. Place the pretrained `.pt` file in the same directory as `generator.py`.
2. Modify context sizes and `.pth` file names in the `__main__` section of `generator.py` to test various context sizes.
3. Ensure that any required dependencies are installed before running the script.

