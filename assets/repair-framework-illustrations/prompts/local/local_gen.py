"""Local Xiaohei illustrations with Z-Image-Turbo (Q5_K_M GGUF) on an 8 GB GPU.

usage: python local_gen.py <name>[,<name>...] [--seeds 1,2,3] [--w 1280 --h 720]

Phase 1 encodes the prompts on the CPU with the full-precision text encoder and
caches the embeddings in local/emb/. Phase 2 loads only the quantized image model
on the GPU and renders each prompt once per seed into raw/local/.
"""
import argparse, gc, time
from pathlib import Path

import torch
from huggingface_hub import hf_hub_download, snapshot_download

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "local"
OUT = HERE / "raw" / "local"
BASE = snapshot_download("Tongyi-MAI/Z-Image-Turbo", allow_patterns=["model_index.json", "scheduler/*", "text_encoder/*",
                         "tokenizer/*", "vae/*", "transformer/config.json"])
GGUF = hf_hub_download("unsloth/Z-Image-Turbo-GGUF", "z-image-turbo-Q5_K_M.gguf", local_files_only=True)


def prompt_for(name):
    return (LOCAL / "_style.txt").read_text(encoding="utf-8").strip() + "\n\n" + \
           (LOCAL / f"{name}.txt").read_text(encoding="utf-8").strip()


def encode(names):
    from diffusers import ZImagePipeline
    emb_dir = LOCAL / "emb"
    emb_dir.mkdir(exist_ok=True)
    todo = [n for n in names
            if not (emb_dir / f"{n}.pt").exists()
            or (emb_dir / f"{n}.pt").stat().st_mtime < (LOCAL / f"{n}.txt").stat().st_mtime
            or (emb_dir / f"{n}.pt").stat().st_mtime < (LOCAL / "_style.txt").stat().st_mtime]
    if todo:
        pipe = ZImagePipeline.from_pretrained(BASE, transformer=None, torch_dtype=torch.bfloat16)
        for n in todo:
            text = prompt_for(n)
            ids = pipe.tokenizer.apply_chat_template([{"role": "user", "content": text}], tokenize=True,
                                                     add_generation_prompt=True, enable_thinking=True)
            ntok = len(ids["input_ids"] if isinstance(ids, dict) else ids)
            t = time.time()
            with torch.inference_mode():
                emb, _ = pipe.encode_prompt(text, device="cpu", do_classifier_free_guidance=False,
                                            max_sequence_length=1024)
            torch.save([e.cpu() for e in emb], emb_dir / f"{n}.pt")
            print(f"encoded {n}: {ntok} tokens, {time.time() - t:.0f}s", flush=True)
        del pipe
        gc.collect()
    return {n: torch.load(emb_dir / f"{n}.pt") for n in names}


def render(embs, seeds, w, h):
    from diffusers import ZImagePipeline, ZImageTransformer2DModel, GGUFQuantizationConfig
    transformer = ZImageTransformer2DModel.from_single_file(
        GGUF, quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
        torch_dtype=torch.bfloat16, config=BASE, subfolder="transformer")
    pipe = ZImagePipeline.from_pretrained(BASE, transformer=transformer, text_encoder=None,
                                          torch_dtype=torch.bfloat16)
    pipe.to("cuda")
    OUT.mkdir(parents=True, exist_ok=True)
    for name, emb in embs.items():
        for seed in seeds:
            out = OUT / f"{name}__s{seed}.png"
            if out.exists():
                continue
            t = time.time()
            with torch.inference_mode():
                img = pipe(prompt_embeds=[e.to("cuda", torch.bfloat16) for e in emb], width=w, height=h,
                           num_inference_steps=9, guidance_scale=0.0,
                           generator=torch.Generator("cuda").manual_seed(seed)).images[0]
            img.save(out)
            print(f"{out.name}  {time.time() - t:.0f}s  peak VRAM {torch.cuda.max_memory_allocated() / 1e9:.1f} GB",
                  flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("names")
    ap.add_argument("--seeds", default="1")
    ap.add_argument("--w", type=int, default=1280)
    ap.add_argument("--h", type=int, default=720)
    a = ap.parse_args()
    embs = encode(a.names.split(","))
    render(embs, [int(s) for s in a.seeds.split(",")], a.w, a.h)
