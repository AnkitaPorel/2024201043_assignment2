import os
import sys
import re
import random
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from collections import defaultdict
from torch.utils.data import Dataset, DataLoader, random_split
from collections import Counter
import torch.nn.functional as F

CONTRACTIONS = {
    "i'm": "i am",
    "you're": "you are",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "we're": "we are",
    "they're": "they are",
    "i've": "i have",
    "you've": "you have",
    "we've": "we have",
    "they've": "they have",
    "i'd": "i would",
    "you'd": "you would",
    "he'd": "he would",
    "she'd": "she would",
    "we'd": "we would",
    "they'd": "they would",
    "i'll": "i will",
    "you'll": "you will",
    "he'll": "he will",
    "she'll": "she will",
    "we'll": "we will",
    "they'll": "they will",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "haven't": "have not",
    "hasn't": "has not",
    "hadn't": "had not",
    "won't": "will not",
    "wouldn't": "would not",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "can't": "cannot",
    "couldn't": "could not",
    "shouldn't": "should not",
    "mightn't": "might not",
    "mustn't": "must not",
    "shan't": "shall not",
}

class LSTMLanguageModel(nn.Module):
    def __init__(
        self,
        vocab_size,
        embedding_dim,
        hidden_dim,
        num_layers=1,
        dropout_rate=0.5,
    ):
        super(LSTMLanguageModel, self).__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim)
        self.lstm = nn.LSTM(
            embedding_dim, hidden_dim, num_layers=num_layers, batch_first=True, dropout=dropout_rate
        )
        self.fc = nn.Linear(hidden_dim, vocab_size)
        self.dropout = nn.Dropout(dropout_rate)
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

    def forward(self, x, hidden=None):
        embedded = self.embedding(x)
        if hidden is None:
            hidden = self.init_hidden(x.size(0))
        output, hidden = self.lstm(embedded, hidden)
        output = self.dropout(output)
        logits = self.fc(output)
        return logits, hidden

    def init_hidden(self, batch_size):
        return (
            torch.zeros(self.num_layers, batch_size, self.hidden_dim),
            torch.zeros(self.num_layers, batch_size, self.hidden_dim),
        )

def setup_training_lstm(
    train_data_token, vocab, context_size, embedding_dim=100, hidden_dim=128
):
    dataset = NGramDataset(train_data_token, vocab, context_size)

    total_size = len(dataset)
    train_size = int(0.7 * total_size)
    val_size = total_size - train_size

    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

    batch_size = 32
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    model = LSTMLanguageModel(
        len(vocab), embedding_dim, hidden_dim, num_layers=1, dropout_rate=0.2
    )

    word_counts = Counter(train_data_token)
    total_words = len(train_data_token)
    weights = torch.tensor(
        [1 - (word_counts[word] / total_words) for word in vocab], dtype=torch.float
    )
    criterion = nn.CrossEntropyLoss(weight=weights)

    optimizer = optim.AdamW(model.parameters(), lr=0.1, weight_decay=0.08)

    return model, train_loader, val_loader, criterion, optimizer

def train_with_validation_lstm(
    model, train_loader, val_loader, criterion, optimizer, epochs=10, patience=3
):
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.1, patience=1
    )
    best_val_loss = float("inf")
    patience_counter = 0
    training_losses = []
    validation_losses = []

    for epoch in range(epochs):
        model.train()
        total_train_loss = 0
        for context, target in train_loader:
            optimizer.zero_grad()
            hidden = model.init_hidden(context.size(0))
            output, hidden = model(context, hidden)
            output = output[:, -1, :]
            loss = criterion(output, target)
            loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            optimizer.step()
            total_train_loss += loss.item()

        avg_train_loss = total_train_loss / len(train_loader)
        training_losses.append(avg_train_loss)

        model.eval()
        total_val_loss = 0
        with torch.no_grad():
            for context, target in val_loader:
                hidden = model.init_hidden(context.size(0))
                output, hidden = model(context, hidden)
                output = output[:, -1, :]
                loss = criterion(output, target)
                total_val_loss += loss.item()

        avg_val_loss = total_val_loss / len(val_loader)
        validation_losses.append(avg_val_loss)

        print(f"Epoch {epoch + 1}/{epochs}")
        print(f"Training Loss: {avg_train_loss:.4f}")
        print(f"Validation Loss: {avg_val_loss:.4f}")

        scheduler.step(avg_val_loss)

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            torch.save(model.state_dict(), "best_lstm_lm.pth")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping triggered after epoch {epoch + 1}")
                break

    return training_losses, validation_losses

def calculate_perplexity_lstm(model, sentence, vocab, context_size):
    model.eval()
    words = sentence.lower().split()
    
    words = [word if word in vocab else "<unk>" for word in words]
    
    if len(words) <= context_size:
        return float('inf')
    
    total_log_prob = 0.0
    num_predictions = 0
    
    with torch.no_grad():
        hidden = model.init_hidden(1)
        for i in range(context_size, len(words)):
            context = words[i - context_size:i]
            target = words[i]
            
            context_ids = [vocab[word] for word in context]
            context_tensor = torch.tensor([context_ids], dtype=torch.long)
            target_id = vocab[target]
            
            output, hidden = model(context_tensor, hidden)
            output = output[:, -1, :]

            log_probs = F.log_softmax(output, dim=1)
            total_log_prob += log_probs[0][target_id].item()
            num_predictions += 1
    
    avg_neg_log_likelihood = -total_log_prob / num_predictions
    
    perplexity = torch.exp(torch.tensor(avg_neg_log_likelihood)).item()
    
    return perplexity

def evaluate_model_perplexity_lstm(model, test_sentences, vocab, context_size, filename):
    total_perplexity = 0
    valid_sentences = 0
    with open(filename, 'w', encoding='utf-8') as f:
        for sentence in test_sentences:
            perplexity = calculate_perplexity_lstm(model, sentence, vocab, context_size)
            f.write(f"{sentence} | {perplexity}\n")
            if perplexity != float('inf') and perplexity < 10000:
                total_perplexity += perplexity
                valid_sentences += 1
    
    return total_perplexity / valid_sentences if valid_sentences > 0 else float('inf')

def predict_top_k_words_lstm(model, sentence, vocab, context_size, k=5):
    model.eval()
    words = sentence.lower().split()
    if len(words) < context_size:
        padding_token = "<unk>"
        words = [padding_token] * (context_size - len(words)) + words
    words = [word if word in vocab else "<unk>" for word in words]
    
    context = words[-context_size:]
    context_ids = [vocab[word] for word in context]
    context_tensor = torch.tensor([context_ids], dtype=torch.long)
    
    with torch.no_grad():
        hidden = model.init_hidden(1)
        output, hidden = model(context_tensor, hidden)
        output = output[:, -1, :]
        
        probs = F.softmax(output, dim=1)
        top_k_probs, top_k_indices = torch.topk(probs, k, dim=1)
        
        idx_to_word = {idx: word for word, idx in vocab.items()}
        top_k_words = [idx_to_word[idx.item()] for idx in top_k_indices[0]]
        
        return list(zip(top_k_words, top_k_probs[0].tolist()))

class RNNLanguageModel(nn.Module):
    def __init__(
        self,
        vocab_size,
        embedding_dim,
        hidden_dim,
        num_layers=1,
        dropout_rate=0.5,
    ):
        super(RNNLanguageModel, self).__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim)
        self.rnn = nn.RNN(
            embedding_dim, hidden_dim, num_layers=num_layers, batch_first=True, dropout=dropout_rate
        )
        self.fc = nn.Linear(hidden_dim, vocab_size)
        self.dropout = nn.Dropout(dropout_rate)
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

    def forward(self, x, hidden=None):
        embedded = self.embedding(x)
        if hidden is None:
            hidden = self.init_hidden(x.size(0))
        output, hidden = self.rnn(embedded, hidden)
        output = self.dropout(output)
        logits = self.fc(output)
        return logits, hidden

    def init_hidden(self, batch_size):
        return torch.zeros(self.num_layers, batch_size, self.hidden_dim)

def setup_training_rnn(
    train_data_token, vocab, context_size, embedding_dim=100, hidden_dim=128
):
    dataset = NGramDataset(train_data_token, vocab, context_size)

    total_size = len(dataset)
    train_size = int(0.7 * total_size)
    val_size = total_size - train_size

    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

    batch_size = 32
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    model = RNNLanguageModel(
        len(vocab), embedding_dim, hidden_dim, num_layers=1, dropout_rate=0.2
    )

    word_counts = Counter(train_data_token)
    total_words = len(train_data_token)
    weights = torch.tensor(
        [1 - (word_counts[word] / total_words) for word in vocab], dtype=torch.float
    )
    criterion = nn.CrossEntropyLoss(weight=weights)

    optimizer = optim.AdamW(model.parameters(), lr=0.1, weight_decay=0.08)

    return model, train_loader, val_loader, criterion, optimizer


def train_with_validation_rnn(
    model, train_loader, val_loader, criterion, optimizer, epochs=10, patience=3
):
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.1, patience=1
    )
    best_val_loss = float("inf")
    patience_counter = 0
    training_losses = []
    validation_losses = []

    for epoch in range(epochs):
        model.train()
        total_train_loss = 0
        for context, target in train_loader:
            optimizer.zero_grad()
            hidden = model.init_hidden(context.size(0))
            output, hidden = model(context, hidden)
            output = output[:, -1, :]
            loss = criterion(output, target)
            loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            optimizer.step()
            total_train_loss += loss.item()

        avg_train_loss = total_train_loss / len(train_loader)
        training_losses.append(avg_train_loss)

        model.eval()
        total_val_loss = 0
        with torch.no_grad():
            for context, target in val_loader:
                hidden = model.init_hidden(context.size(0))
                output, hidden = model(context, hidden)
                output = output[:, -1, :]
                loss = criterion(output, target)
                total_val_loss += loss.item()

        avg_val_loss = total_val_loss / len(val_loader)
        validation_losses.append(avg_val_loss)

        print(f"Epoch {epoch + 1}/{epochs}")
        print(f"Training Loss: {avg_train_loss:.4f}")
        print(f"Validation Loss: {avg_val_loss:.4f}")

        scheduler.step(avg_val_loss)

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            torch.save(model.state_dict(), "best_rnn_lm.pth")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping triggered after epoch {epoch + 1}")
                break

    return training_losses, validation_losses


def calculate_perplexity_rnn(model, sentence, vocab, context_size):
    model.eval()
    words = sentence.lower().split()

    words = [word if word in vocab else "<unk>" for word in words]
    
    if len(words) <= context_size:
        return float('inf')
    
    total_log_prob = 0.0
    num_predictions = 0
    
    with torch.no_grad():
        hidden = model.init_hidden(1)
        for i in range(context_size, len(words)):
            context = words[i - context_size:i]
            target = words[i]

            context_ids = [vocab[word] for word in context]
            context_tensor = torch.tensor([context_ids], dtype=torch.long)
            target_id = vocab[target]

            output, hidden = model(context_tensor, hidden)
            output = output[:, -1, :]
            
            log_probs = F.log_softmax(output, dim=1)
            total_log_prob += log_probs[0][target_id].item()
            num_predictions += 1
    
    avg_neg_log_likelihood = -total_log_prob / num_predictions
    
    perplexity = torch.exp(torch.tensor(avg_neg_log_likelihood)).item()
    
    return perplexity


def evaluate_model_perplexity_rnn(model, test_sentences, vocab, context_size, filename):
    total_perplexity = 0
    valid_sentences = 0
    with open(filename, 'w', encoding='utf-8') as f:
        for sentence in test_sentences:
            perplexity = calculate_perplexity_rnn(model, sentence, vocab, context_size)
            f.write(f"{sentence} | {perplexity}\n")
            if perplexity != float('inf') and perplexity < 10000:
                total_perplexity += perplexity
                valid_sentences += 1
    
    return total_perplexity / valid_sentences if valid_sentences > 0 else float('inf')

def predict_top_k_words_rnn(model, sentence, vocab, context_size, k=5):
    model.eval()
    words = sentence.lower().split()
    if len(words) < context_size:
        padding_token = "<unk>"
        words = [padding_token] * (context_size - len(words)) + words
    words = [word if word in vocab else "<unk>" for word in words]
    
    context = words[-context_size:]
    context_ids = [vocab[word] for word in context]
    context_tensor = torch.tensor([context_ids], dtype=torch.long)
    
    with torch.no_grad():
        hidden = model.init_hidden(1)
        output, hidden = model(context_tensor, hidden)
        output = output[:, -1, :]
        
        probs = F.softmax(output, dim=1)
        top_k_probs, top_k_indices = torch.topk(probs, k, dim=1)
        
        idx_to_word = {idx: word for word, idx in vocab.items()}
        top_k_words = [idx_to_word[idx.item()] for idx in top_k_indices[0]]
        
        return list(zip(top_k_words, top_k_probs[0].tolist()))

def expand_contractions(text):
    for contraction, expansion in CONTRACTIONS.items():
        text = re.sub(rf"\b{contraction}\b", expansion, text, flags=re.IGNORECASE)
    return text

class NGramDataset(Dataset):
    def __init__(self, corpus, vocab, context_size):
        self.data = []
        self.vocab = vocab
        self.context_size = context_size

        for i in range(context_size, len(corpus)):
            context = corpus[i - context_size : i]
            target = corpus[i]
            self.data.append((context, target))

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        context, target = self.data[idx]
        context_ids = [self.vocab[word] for word in context]
        target_id = self.vocab[target]
        return torch.tensor(context_ids, dtype=torch.long), torch.tensor(
            target_id, dtype=torch.long
        )

def build_vocab(corpus):
    vocab = defaultdict(lambda: len(vocab))
    vocab["<unk>"] = 0
    for word in corpus:
        vocab[word]
    return vocab

class FFNNLanguageModel(nn.Module):
    def __init__(
        self,
        vocab_size,
        embedding_dim,
        hidden_dim,
        context_size,
        dropout_rate=0.5,
    ):
        super(FFNNLanguageModel, self).__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim)

        self.batch_norm1 = nn.BatchNorm1d(context_size * embedding_dim)
        self.batch_norm2 = nn.BatchNorm1d(hidden_dim)

        self.fc1 = nn.Linear(context_size * embedding_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim // 2)
        self.fc3 = nn.Linear(hidden_dim // 2, vocab_size)

        self.dropout = nn.Dropout(dropout_rate)

        self.activation = nn.ReLU()

    def forward(self, x):
        embedded = self.embedding(x).view(x.size(0), -1)
        embedded = self.batch_norm1(embedded)

        out = self.fc1(embedded)
        out = self.batch_norm2(out)
        out = self.activation(out)
        out = self.dropout(out)

        out = self.fc2(out)
        out = self.activation(out)
        out = self.dropout(out)

        out = self.fc3(out)
        return out

def preprocess(corpus_text):
    url_pattern = r"(https?://\S+?)([.,!?;])?(?=\s|$)"
    www_url_pattern = r"www\.\S+?(\s|$)"
    hashtag_pattern = r"#\w+"
    mention_pattern = r"@\w+"
    percentage_pattern = r"\b\d+(\.\d+)?%"
    time_pattern = r"\b\d{1,2}:\d{2}(?:\s?[APap][Mm])?"
    age_pattern = r"\b\d{1,3}\s?(?:years?\s?old|y/o)\b"
    time_period_pattern = r"\b\d{1,4}\s?(?:BC|AD|BCE|CE)\b"

    corpus_text = re.sub(
        r"\bchapter\s+[IVXLCDM]+\b.*(?:\n|$)", "", corpus_text, flags=re.IGNORECASE
    )

    corpus_text = re.sub(url_pattern, r"<URL>\2", corpus_text)
    corpus_text = re.sub(www_url_pattern, "", corpus_text)
    corpus_text = re.sub(hashtag_pattern, "<HASHTAG>", corpus_text)
    corpus_text = re.sub(mention_pattern, "<MENTION>", corpus_text)
    corpus_text = re.sub(percentage_pattern, "<PERCENTAGE>", corpus_text)
    corpus_text = re.sub(time_pattern, "<TIME>", corpus_text)
    corpus_text = re.sub(age_pattern, "<AGE>", corpus_text)
    corpus_text = re.sub(time_period_pattern, "<TIME_PERIOD>", corpus_text)
    corpus_text = re.sub(r"’", "'", corpus_text)
    corpus_text = expand_contractions(corpus_text)
    corpus_text = re.sub(r"'", "", corpus_text)
    corpus_text = re.sub(r'[\'"]', "", corpus_text)

    corpus_text = re.sub(r"[\(\)\[\]\{\}]", "", corpus_text)
    corpus_text = re.sub(r"(?<=\w)-(?=\w)", "", corpus_text)
    corpus_text = re.sub(r"(<[A-Z_]+>)([.,!?;])", r"\1", corpus_text)
    corpus_text = re.sub(r"_([^_]+)_", r"\1", corpus_text)
    corpus_text = re.sub(r"\n+", " ", corpus_text)
    corpus_text = re.sub(r"\d+", "", corpus_text)
    corpus_text = re.sub(r"\s+", " ", corpus_text).strip()

    sentences = re.split(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|!)\s", corpus_text)
    sentences = [sentence.strip() for sentence in sentences]
    sentences = [re.sub(r"[.,?,!,;,*,—]", "", sentence) for sentence in sentences]
    sentences = [re.sub(r"-+", " ", sentence) for sentence in sentences]
    sentences = [re.sub(r":", " ", sentence) for sentence in sentences]
    sentences = [re.sub(r"\s+", " ", sentence).strip() for sentence in sentences]

    sentences = [sentence.lower() for sentence in sentences]

    return sentences

def train_with_validation(
    model, train_loader, val_loader, criterion, optimizer, epochs=10, patience=3
):
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.1, patience=1
    )
    best_val_loss = float("inf")
    patience_counter = 0
    training_losses = []
    validation_losses = []

    for epoch in range(epochs):
        model.train()
        total_train_loss = 0
        for context, target in train_loader:
            optimizer.zero_grad()
            output = model(context)
            loss = criterion(output, target)
            loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            optimizer.step()
            total_train_loss += loss.item()

        avg_train_loss = total_train_loss / len(train_loader)
        training_losses.append(avg_train_loss)

        model.eval()
        total_val_loss = 0
        with torch.no_grad():
            for context, target in val_loader:
                output = model(context)
                loss = criterion(output, target)
                total_val_loss += loss.item()

        avg_val_loss = total_val_loss / len(val_loader)
        validation_losses.append(avg_val_loss)

        print(f"Epoch {epoch + 1}/{epochs}")
        print(f"Training Loss: {avg_train_loss:.4f}")
        print(f"Validation Loss: {avg_val_loss:.4f}")

        scheduler.step(avg_val_loss)

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            torch.save(model.state_dict(), "best_ffnn_lm.pth")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping triggered after epoch {epoch + 1}")
                break

    return training_losses, validation_losses

def setup_training(
    train_data_token, vocab, context_size, embedding_dim=100, hidden_dim=128
):
    dataset = NGramDataset(train_data_token, vocab, context_size)

    total_size = len(dataset)
    train_size = int(0.7 * total_size)
    val_size = total_size - train_size

    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

    batch_size = 32
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    model = FFNNLanguageModel(
        len(vocab), embedding_dim, hidden_dim, context_size, dropout_rate=0.2
    )

    word_counts = Counter(train_data_token)
    total_words = len(train_data_token)
    weights = torch.tensor(
        [1 - (word_counts[word] / total_words) for word in vocab], dtype=torch.float
    )
    criterion = nn.CrossEntropyLoss(weight=weights)

    optimizer = optim.AdamW(model.parameters(), lr=0.1, weight_decay=0.08)

    return model, train_loader, val_loader, criterion, optimizer

def calculate_perplexity(model, sentence, vocab, context_size):
    model.eval()
    words = sentence.lower().split()
    
    words = [word if word in vocab else "<unk>" for word in words]
    
    if len(words) <= context_size:
        return float('inf')
    
    total_log_prob = 0.0
    num_predictions = 0
    
    with torch.no_grad():
        for i in range(context_size, len(words)):
            context = words[i - context_size:i]
            target = words[i]
            
            context_ids = [vocab[word] for word in context]
            context_tensor = torch.tensor([context_ids], dtype=torch.long)
            target_id = vocab[target]
            
            output = model(context_tensor)
            
            log_probs = F.log_softmax(output, dim=1)
            total_log_prob += log_probs[0][target_id].item()
            num_predictions += 1
    
    avg_neg_log_likelihood = -total_log_prob / num_predictions
    
    perplexity = torch.exp(torch.tensor(avg_neg_log_likelihood)).item()
    
    return perplexity

def evaluate_model_perplexity(model, test_sentences, vocab, context_size, filename):
    total_perplexity = 0
    valid_sentences = 0
    with open(filename, 'w', encoding='utf-8') as f:
        for sentence in test_sentences:
            perplexity = calculate_perplexity(model, sentence, vocab, context_size)
            f.write(f"{sentence} | {perplexity}\n")
            if perplexity != float('inf') and perplexity < 10000:
                total_perplexity += perplexity
                valid_sentences += 1
    
    return total_perplexity / valid_sentences if valid_sentences > 0 else float('inf')

def load_vocab_from_file(vocab_file):
    vocab = {}
    with open(vocab_file, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            word = line.strip()
            vocab[word] = idx
    return vocab

def save_vocab_to_file(vocab, vocab_file):
    idx_to_word = {idx: word for word, idx in vocab.items()}
    with open(vocab_file, 'w', encoding='utf-8') as f:
        for idx in range(len(vocab)):
            f.write(f"{idx_to_word[idx]}\n")

def build_vocab_with_size(corpus, target_size):
    word_counts = Counter(corpus)
    
    sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    
    vocab = defaultdict(lambda: 0)
    vocab["<unk>"] = 0
    
    for word, _ in sorted_words[:target_size-1]:
        vocab[word] = len(vocab)

    return dict(vocab)

def predict_next_word(model, sentence, vocab, context_size, vocab_size, k=5):
    model.eval()
    words = sentence.lower().split()
    if len(words) < context_size:
        padding_token = "<unk>"
        words = [padding_token] * (context_size - len(words)) + words
    words = [word if word in vocab else "<unk>" for word in words]
    
    context = words[-context_size:]
    context_ids = [vocab[word] for word in context]
    context_tensor = torch.tensor([context_ids], dtype=torch.long)
    
    with torch.no_grad():
        output = model(context_tensor)
        temperature = 0.5
        probs = F.softmax(output / temperature, dim=1)
        top_k_probs, top_k_indices = torch.topk(probs, k, dim=1)
        
        idx_to_word = {idx: word for word, idx in vocab.items()}
        top_k_words = [idx_to_word[idx.item()] for idx in top_k_indices[0]]
        
        return list(zip(top_k_words, top_k_probs[0].tolist()))

def print_predictions(predictions):
    for word, prob in predictions:
        print(f"Word: {word} | Probability: {prob:.4f}")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 generator.py <lm_type> <corpus_path> <k>")
        sys.exit(0)

    lm_type = sys.argv[1]
    corpus_path = sys.argv[2]
    k = int(sys.argv[3])
    corpus_text = ""
    if not os.path.isfile(corpus_path):
        raise ValueError("Invalid corpus path provided.")
    with open(corpus_path, "r", encoding="utf-8") as file:
        corpus_text = file.read()

    sentences = preprocess(corpus_text)

    test_data = random.sample(sentences, 1000)
    train_data = [s for s in sentences if s not in test_data]

    train_data_string = ""
    for s in train_data:
        train_data_string += s

    train_data_token = train_data_string.split()
    if lm_type == "-f":
        saved_state_dict = torch.load("ffnn_lm3.pth")
        saved_vocab_size = saved_state_dict['embedding.weight'].shape[0]
        
        vocab = build_vocab_with_size(train_data_token, saved_vocab_size)
        
        model = FFNNLanguageModel(
            vocab_size=saved_vocab_size,
            embedding_dim=100,
            hidden_dim=128,
            context_size=3,
            dropout_rate=0.2
        )
        
        model.load_state_dict(saved_state_dict)
        model.eval()
        
        input_sentence = input("Input sentence: ")
        sentence = preprocess(input_sentence)
        predictions = predict_next_word(model, input_sentence, vocab, 3, saved_vocab_size, k)
        print_predictions(predictions)

    if lm_type == '-r':
        saved_state_dict = torch.load("rnn_lm3.pth")
        saved_vocab_size = saved_state_dict['embedding.weight'].shape[0]

        vocab = build_vocab_with_size(train_data_token, saved_vocab_size)
        word_counts = Counter(train_data_token)
        train_data_token = [
            word if word_counts[word] >= 2 else "<unk>" for word in train_data_token
        ]
        context_size = 3
        model = RNNLanguageModel(
            vocab_size=saved_vocab_size,
            embedding_dim=100,
            hidden_dim=128,
            num_layers=1,
            dropout_rate=0.2
        )

        model.load_state_dict(saved_state_dict)
        model.eval()

        input_sentence = input("Input sentence: ")
        predictions = predict_top_k_words_rnn(model, input_sentence, vocab, context_size, k)
        print_predictions(predictions)

    if lm_type == '-l':
        saved_state_dict = torch.load("lstm_lm3.pth")
        saved_vocab_size = saved_state_dict['embedding.weight'].shape[0]

        vocab = build_vocab_with_size(train_data_token, saved_vocab_size)

        model = LSTMLanguageModel(
            vocab_size=saved_vocab_size,
            embedding_dim=100,
            hidden_dim=128,
            num_layers=1,
            dropout_rate=0.2
        )

        model.load_state_dict(saved_state_dict)
        model.eval()

        input_sentence = input("Input sentence: ")
        predictions = predict_top_k_words_lstm(model, input_sentence, vocab, 3, k)
        print_predictions(predictions)
