"""Minimal Gradio front-end for local ``process_mesh`` runs (optional dependency)."""

from __future__ import annotations

from pathlib import Path


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
        sample_count: int,
        build: bool,
        auto_tune: bool,
        align_icp: bool,
        icp_iterations: int,
        icp_seed: int,
    ) -> dict:
        p = Path(input_path).expanduser()
        if not p.is_file():
            return {"error": f"Not a file: {p}"}
        return process_mesh(
            input_path=p,
            output_dir=None,
            sample_count=int(sample_count),
            simplify_target_faces=None,
            build=bool(build),
            auto_tune_sampling=bool(auto_tune),
            align_surface_metrics=bool(align_icp),
            icp_iterations=int(icp_iterations),
            icp_seed=int(icp_seed),
        )

    with gr.Blocks(title="ViminCADConverter") as demo:
        gr.Markdown(
            "# ViminCADConverter (local)\nRun analysis on a mesh or point-cloud path on this machine."
        )
        path = gr.Textbox(label="Input path (STL/OBJ/PLY or .xyz/.pts/.csv/.npy)")
        sample_count = gr.Number(label="Sample count", value=5000, precision=0)
        build = gr.Checkbox(label="Run CAD build (requires build123d)", value=False)
        auto_tune = gr.Checkbox(label="Auto-tune sample count to mesh size", value=True)
        align_icp = gr.Checkbox(label="ICP-aligned surface metrics in validation", value=True)
        icp_iterations = gr.Number(label="ICP iterations", value=10, precision=0)
        icp_seed = gr.Number(label="ICP seed (reserved)", value=0, precision=0)
        out = gr.JSON(label="Result")
        gr.Button("Run").click(
            run_sync,
            inputs=[path, sample_count, build, auto_tune, align_icp, icp_iterations, icp_seed],
            outputs=out,
        )
    demo.launch(server_name="127.0.0.1", server_port=7860)


if __name__ == "__main__":
    main()
