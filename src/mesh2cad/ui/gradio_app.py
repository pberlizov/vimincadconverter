"""Gradio front-end for local ``process_mesh`` runs (optional dependency)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any


def _uploaded_input_path(upload_file: Any) -> Path | None:
    if upload_file is None:
        return None
    if isinstance(upload_file, str):
        p = Path(upload_file)
        return p if p.is_file() else None
    if isinstance(upload_file, Path):
        return upload_file if upload_file.is_file() else None
    for attr in ("path", "name"):
        v = getattr(upload_file, attr, None)
        if isinstance(v, str):
            p = Path(v)
            if p.is_file():
                return p
    if isinstance(upload_file, dict):
        for key in ("path", "name"):
            v = upload_file.get(key)
            if isinstance(v, str):
                p = Path(v)
                if p.is_file():
                    return p
    return None


def main() -> None:
    try:
        import gradio as gr
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Gradio is not installed. Use: pip install gradio  (or pip install -e \".[full]\")"
        ) from exc

    from mesh2cad.api.service import process_mesh

    def run_sync(
        input_path: str,
        upload_file: Any,
        sample_count: float,
        build: bool,
        auto_tune: bool,
        align_icp: bool,
        icp_iterations: float,
        icp_seed: float,
    ) -> tuple[dict[str, Any], str | None, str | None, str | None, str | None]:
        up = _uploaded_input_path(upload_file)
        if up is not None:
            src = up
        else:
            raw = (input_path or "").strip()
            if not raw:
                err = {"error": "Provide an input path or upload a file."}
                return err, None, None, None, None
            src = Path(raw).expanduser()
            if not src.is_file():
                err = {"error": f"Not a file: {src}"}
                return err, None, None, None, None

        state_root = Path(
            os.environ.get("MESH2CAD_STATE_DIR", tempfile.gettempdir())
        ).expanduser()
        work = state_root / "mesh2cad_gradio" / uuid.uuid4().hex
        work.mkdir(parents=True, exist_ok=True)
        staged = work / src.name
        shutil.copy2(src, staged)

        out_dir: Path | None = (work / "out") if build else None
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)

        payload = process_mesh(
            input_path=staged,
            output_dir=out_dir,
            sample_count=int(sample_count),
            simplify_target_faces=None,
            build=bool(build),
            auto_tune_sampling=bool(auto_tune),
            align_surface_metrics=bool(align_icp),
            icp_iterations=int(icp_iterations),
            icp_seed=int(icp_seed),
        )

        report_path = work / "report.json"
        report_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

        script_path: str | None = None
        step_path: str | None = None
        preview_path: str | None = None
        b = payload.get("build")
        if isinstance(b, dict):
            sc = b.get("script")
            if isinstance(sc, str) and sc.strip():
                sp = work / "reconstruction.py"
                sp.write_text(sc, encoding="utf-8")
                script_path = str(sp)
            sp_step = b.get("step_path")
            if isinstance(sp_step, str) and Path(sp_step).is_file():
                step_path = sp_step
            md = b.get("metadata")
            if isinstance(md, dict):
                pv = md.get("preview_stl_path")
                if isinstance(pv, str) and Path(pv).is_file():
                    preview_path = pv

        return payload, str(report_path), script_path, step_path, preview_path

    with gr.Blocks(title="ViminCADConverter") as demo:
        gr.Markdown(
            "# ViminCADConverter (local)\n"
            "Analyze a mesh or point cloud. **Upload a file** or enter a path on this machine. "
            "When **Run CAD build** is enabled, exports appear as downloads (STEP / preview STL / script)."
        )
        path = gr.Textbox(
            label="Input path (ignored if a file is uploaded)",
            placeholder="STL/OBJ/PLY or .xyz/.pts/.csv/.npy",
        )
        upload = gr.File(
            label="Upload mesh or point cloud",
            file_count="single",
        )
        sample_count = gr.Number(label="Sample count", value=5000, precision=0)
        build = gr.Checkbox(label="Run CAD build (requires build123d)", value=False)
        auto_tune = gr.Checkbox(label="Auto-tune sample count to mesh size", value=True)
        align_icp = gr.Checkbox(label="ICP-aligned surface metrics in validation", value=True)
        icp_iterations = gr.Number(label="ICP iterations", value=10, precision=0)
        icp_seed = gr.Number(label="ICP seed", value=0, precision=0)
        out = gr.JSON(label="Result")
        report_dl = gr.File(label="Download report.json")
        script_dl = gr.File(label="Download reconstruction.py (after build)")
        step_dl = gr.File(label="Download STEP (after build)")
        preview_dl = gr.File(label="Download preview STL (after build)")
        gr.Button("Run").click(
            run_sync,
            inputs=[
                path,
                upload,
                sample_count,
                build,
                auto_tune,
                align_icp,
                icp_iterations,
                icp_seed,
            ],
            outputs=[out, report_dl, script_dl, step_dl, preview_dl],
        )
    demo.launch(server_name="127.0.0.1", server_port=7860)


if __name__ == "__main__":
    main()
