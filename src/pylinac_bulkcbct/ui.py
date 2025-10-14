"""Simple web UI for running CBCT inventory scans."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from flask import Flask, Response, flash, redirect, render_template_string, request, url_for

try:  # pragma: no cover - exercised when running as script
    from .inventory import DEFAULT_EXTENSIONS, StudyInventory, build_inventory
except ImportError:  # pragma: no cover - fallback for direct execution
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from pylinac_bulkcbct.inventory import (  # type: ignore[import-not-found]
        DEFAULT_EXTENSIONS,
        StudyInventory,
        build_inventory,
    )


_FALLBACK_CTPHAN_MODELS: tuple[tuple[str, str], ...] = (
    ("CatPhan503", "Catphan 503"),
    ("CatPhan504", "Catphan 504"),
    ("CatPhan600", "Catphan 600"),
    ("CatPhan604", "Catphan 604"),
    ("CatPhan700", "Catphan 700"),
)


def _discover_catphan_models() -> Sequence[tuple[str, str]]:
    """Return Catphan phantom options available from pylinac."""

    try:
        from pylinac import ct  # type: ignore
    except Exception:  # pragma: no cover - pylinac optional during inventory-only use
        return _FALLBACK_CTPHAN_MODELS

    options: list[tuple[str, str]] = []
    for attr in dir(ct):
        if not attr.startswith("CatPhan"):
            continue
        suffix = attr[7:]
        if not suffix.isdigit():
            continue
        label = f"Catphan {suffix}"
        options.append((attr, label))

    if not options:
        return _FALLBACK_CTPHAN_MODELS

    # Sort by the numeric phantom identifier to keep the menu deterministic.
    options.sort(key=lambda item: int(item[0][7:]))
    # Remove duplicates while preserving order.
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for value, label in options:
        if value in seen:
            continue
        seen.add(value)
        deduped.append((value, label))
    return tuple(deduped)


CATPHAN_MODELS: Sequence[tuple[str, str]] = _discover_catphan_models()


@dataclass
class FormState:
    """Holds the current values submitted via the UI form."""

    root: str = ""
    extensions: str = " ".join(DEFAULT_EXTENSIONS)
    follow_symlinks: bool = False
    phantom: str = CATPHAN_MODELS[0][0] if CATPHAN_MODELS else _FALLBACK_CTPHAN_MODELS[0][0]


def _parse_extensions(raw: str) -> Sequence[str]:
    parts = [part.strip() for part in raw.replace("\n", " ").replace(",", " ").split(" ")]
    return [part for part in parts if part]


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "pylinac-bulkcbct-ui"
    app.config.setdefault("LAST_INVENTORY_JSON", None)

    template = """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>CBCT Inventory Scanner</title>
        <style>
            body { font-family: system-ui, sans-serif; background: #f7f7f7; margin: 0; padding: 0; }
            header { background: #1f4b99; color: white; padding: 1.5rem; }
            main { max-width: 960px; margin: 2rem auto; background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 6px 16px rgba(31,75,153,0.15); }
            h1 { margin-top: 0; }
            form { display: grid; gap: 1.2rem; }
            label { display: block; font-weight: 600; margin-bottom: 0.4rem; }
            input[type=text], textarea, select { width: 100%; padding: 0.6rem 0.8rem; border-radius: 8px; border: 1px solid #ccd6eb; font-size: 1rem; }
            input[type=text]:focus, textarea:focus, select:focus { outline: 2px solid #1f4b99; }
            .checkbox { display: flex; align-items: center; gap: 0.5rem; }
            .actions { display: flex; gap: 0.75rem; align-items: center; }
            button, .button-link { background: #1f4b99; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 999px; font-size: 1rem; cursor: pointer; font-weight: 600; text-decoration: none; display: inline-block; }
            button:hover, .button-link:hover { background: #163a76; }
            .message { padding: 0.75rem 1rem; border-radius: 8px; }
            .message.error { background: #fce8e6; color: #6b1a12; border: 1px solid #f7b5ae; }
            .message.success { background: #e6f4ea; color: #0b5f1a; border: 1px solid #a1d6a3; }
            table { width: 100%; border-collapse: collapse; margin-top: 1.5rem; }
            th, td { border-bottom: 1px solid #e0e6f0; padding: 0.75rem; text-align: left; }
            th { background: #f1f5fb; }
            tbody tr:hover { background: #f9fbff; }
            .inventory-meta { margin-top: 2rem; display: grid; gap: 0.5rem; }
            pre { background: #0f172a; color: #e2e8f0; padding: 1rem; border-radius: 8px; overflow-x: auto; }
        </style>
    </head>
    <body>
        <header>
            <h1>CBCT Inventory Scanner</h1>
            <p>Discover CBCT study folders and review their metadata before bulk processing with Pylinac.</p>
        </header>
        <main>
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                {% for category, message in messages %}
                    <div class="message {{ category }}">{{ message }}</div>
                {% endfor %}
              {% endif %}
            {% endwith %}
            <form method="post" action="{{ url_for('index') }}">
                <div>
                    <label for="root">Scan root directory</label>
                    <input type="text" id="root" name="root" required value="{{ state.root }}" placeholder="/path/to/cbct/root">
                </div>
                <div>
                    <label for="extensions">Image slice extensions</label>
                    <textarea id="extensions" name="extensions" rows="2">{{ state.extensions }}</textarea>
                    <small>Separate multiple extensions with spaces or commas. Use leading dots, e.g. <code>.dcm .ima</code>.</small>
                </div>
                <div>
                    <label for="phantom">Catphan phantom model</label>
                    <select id="phantom" name="phantom">
                        {% for value, label in phantom_options %}
                            <option value="{{ value }}" {% if state.phantom == value %}selected{% endif %}>{{ label }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="checkbox">
                    <input type="checkbox" id="follow_symlinks" name="follow_symlinks" {% if state.follow_symlinks %}checked{% endif %}>
                    <label for="follow_symlinks">Follow symlinks during the scan</label>
                </div>
                <div class="actions">
                    <button type="submit">Run inventory</button>
                    {% if inventory %}
                        <a href="{{ url_for('download_json') }}" class="button-link" download>Download JSON</a>
                    {% endif %}
                </div>
            </form>

            {% if inventory %}
                <section class="inventory-meta">
                    <h2>Scan results</h2>
                    <p><strong>Root:</strong> {{ inventory.root }}</p>
                    <p><strong>Generated:</strong> {{ inventory.generated_at }}</p>
                    <p><strong>Study count:</strong> {{ inventory.study_count }}</p>
                </section>
                {% if inventory.studies %}
                    <table>
                        <thead>
                            <tr>
                                <th>Relative Path</th>
                                <th>File Count</th>
                                <th>Extensions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for study in inventory.studies %}
                                <tr>
                                    <td><code>{{ study.relative_path }}</code></td>
                                    <td>{{ study.file_count }}</td>
                                    <td>{{ ", ".join(study.extensions) }}</td>
                                </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                {% else %}
                    <p>No studies were discovered. Try adjusting the extensions or verifying the directory.</p>
                {% endif %}
                <details>
                    <summary>Raw JSON</summary>
                    <pre>{{ inventory_json }}</pre>
                </details>
            {% endif %}
        </main>
    </body>
    </html>
    """

    def _build_inventory_from_form(state: FormState) -> StudyInventory:
        extensions = _parse_extensions(state.extensions)
        if extensions:
            normalised = [ext if ext.startswith('.') else f'.{ext}' for ext in extensions]
        else:
            normalised = list(DEFAULT_EXTENSIONS)
        return build_inventory(
            Path(state.root),
            extensions=normalised,
            follow_symlinks=state.follow_symlinks,
        )

    @app.route("/", methods=["GET", "POST"])
    def index() -> str:
        state = FormState()
        inventory_dict: dict | None = None
        inventory_json: str | None = None

        if request.method == "POST":
            state.root = request.form.get("root", "").strip()
            state.extensions = request.form.get("extensions", state.extensions)
            state.follow_symlinks = request.form.get("follow_symlinks") == "on"
            state.phantom = request.form.get("phantom", state.phantom)

            if not state.root:
                flash("Please provide a root directory to scan.", "error")
            else:
                try:
                    inventory = _build_inventory_from_form(state)
                except FileNotFoundError:
                    flash("The provided root directory does not exist.", "error")
                except NotADirectoryError:
                    flash("The provided root path is not a directory.", "error")
                except Exception as exc:  # pragma: no cover - defensive
                    flash(f"An unexpected error occurred: {exc}", "error")
                else:
                    inventory_dict = inventory.to_dict()
                    inventory_json = inventory.to_json()
                    app.config["LAST_INVENTORY_JSON"] = inventory_json
                    flash(
                        f"Scan completed successfully with {inventory_dict['study_count']} studies.",
                        "success",
                    )

        return render_template_string(
            template,
            state=state,
            inventory=inventory_dict,
            inventory_json=inventory_json,
            phantom_options=CATPHAN_MODELS,
        )

    @app.route("/download.json")
    def download_json() -> Response:
        inventory_json = app.config.get("LAST_INVENTORY_JSON")
        if inventory_json is None:
            flash("Run a scan before downloading the JSON output.", "error")
            return redirect(url_for("index"))
        return Response(
            inventory_json,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=inventory.json"},
        )

    return app


def main() -> None:
    create_app().run(debug=False, host="0.0.0.0")


__all__: Iterable[str] = ["create_app", "main"]


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    main()

