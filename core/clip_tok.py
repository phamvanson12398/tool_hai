# -*- coding: utf-8 -*-
"""Bộ tách chữ CLIP viết lại thuần Python (theo openai/CLIP simple_tokenizer, giấy phép MIT).

Dùng khi bộ tách chữ của transformers bị lỗi với Stable Diffusion XL (một số bản
transformers 5 trên Windows báo lỗi trong _encode_plus / encode_batch): đọc thẳng
vocab.json + merges.txt của mô hình, không qua transformers / tokenizers.
"""
from __future__ import annotations

import gzip
import html
import json
from functools import lru_cache
from pathlib import Path

try:
    import regex as re          # \p{L} cần thư viện regex (transformers cài sẵn)
except ImportError:  # pragma: no cover
    import re  # type: ignore


@lru_cache()
def _bytes_to_unicode():
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + \
        list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, [chr(c) for c in cs]))


def _pairs(word):
    return {(a, b) for a, b in zip(word, word[1:])}


def _clean(text: str) -> str:
    try:
        import ftfy
        text = ftfy.fix_text(text)
    except Exception:  # noqa: BLE001 — không có ftfy cũng được
        pass
    text = html.unescape(html.unescape(text)).strip()
    return " ".join(text.split()).lower()


class ClipTokenizer:
    def __init__(self, vocab_file: str | Path, merges_file: str | Path, pad_id: int | None = None):
        self.encoder = json.loads(Path(vocab_file).read_text(encoding="utf-8"))
        op = gzip.open if str(merges_file).endswith(".gz") else open
        with op(merges_file, "rt", encoding="utf-8") as f:
            lines = [ln.rstrip("\n") for ln in f]
        merges = [tuple(ln.split()) for ln in lines if ln and not ln.startswith("#version")]
        self.ranks = {m: i for i, m in enumerate(merges) if len(m) == 2}
        self.byte_enc = _bytes_to_unicode()
        self.bos = self.encoder["<|startoftext|>"]
        self.eos = self.encoder["<|endoftext|>"]
        self.pad = self.eos if pad_id is None else pad_id
        self.cache: dict = {}
        self.pat = re.compile(r"""<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[\p{L}]+|[\p{N}]|[^\s\p{L}\p{N}]+""",
                              re.IGNORECASE)

    def _bpe(self, token: str) -> str:
        if token in self.cache:
            return self.cache[token]
        word = tuple(token[:-1]) + (token[-1] + "</w>",)
        pairs = _pairs(word)
        if not pairs:
            return token + "</w>"
        while True:
            bigram = min(pairs, key=lambda p: self.ranks.get(p, float("inf")))
            if bigram not in self.ranks:
                break
            first, second = bigram
            new, i = [], 0
            while i < len(word):
                try:
                    j = word.index(first, i)
                except ValueError:
                    new.extend(word[i:])
                    break
                new.extend(word[i:j])
                i = j
                if word[i] == first and i < len(word) - 1 and word[i + 1] == second:
                    new.append(first + second)
                    i += 2
                else:
                    new.append(word[i])
                    i += 1
            word = tuple(new)
            if len(word) == 1:
                break
            pairs = _pairs(word)
        out = " ".join(word)
        self.cache[token] = out
        return out

    def encode(self, text: str) -> list[int]:
        ids = []
        for tok in re.findall(self.pat, _clean(text)):
            tok = "".join(self.byte_enc[b] for b in tok.encode("utf-8"))
            ids.extend(self.encoder[t] for t in self._bpe(tok).split(" ") if t in self.encoder)
        return ids

    def __call__(self, text: str, length: int = 77) -> list[int]:
        """[bos] + chữ (cắt bớt) + [eos], đệm tới `length`."""
        ids = [self.bos] + self.encode(text)[: length - 2] + [self.eos]
        return ids + [self.pad] * (length - len(ids))
