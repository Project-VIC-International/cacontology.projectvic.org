#!/usr/bin/env python3
"""
CAC Ontology Documentation Generation Script

This script generates comprehensive documentation for the CAC Ontology using Ontospy.
It fetches ontology files from the main CAC-Ontology repository, merges all modules,
and generates HTML documentation matching the CASE Ontology documentation style.
"""

import os
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

try:
    import rdflib
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF, OWL
except ImportError:
    print("Error: rdflib is required. Install with: pip install rdflib")
    sys.exit(1)

# Repository configuration
MAIN_REPO_URL = "https://github.com/Project-VIC-International/CAC-Ontology.git"
ONTOLOGY_REPO_DIR = "ontology_repo"
OUTPUT_DIR = "docs"
TEMP_DIR = tempfile.mkdtemp(prefix="cac_docs_")
ONTOSPY_TIMEOUT_SECONDS = int(os.environ.get("ONTOSPY_TIMEOUT_SECONDS", "1800"))

# Get the repository root directory
REPO_ROOT = Path(__file__).parent.parent


def run_command(cmd: List[str], cwd: Optional[Path] = None, check: bool = True, input_text: Optional[str] = None, timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        input=input_text,
        check=check,
        timeout=timeout
    )
    if result.returncode != 0 and check:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result


def clone_ontology_repo() -> Path:
    """Clone the main ontology repository to fetch latest ontology files."""
    # Check if running in GitHub Actions (ontology repo already checked out)
    env_repo_path = os.environ.get("ONTOLOGY_REPO_PATH")
    if env_repo_path:
        # Resolve relative paths relative to the current working directory
        if not os.path.isabs(env_repo_path):
            # Try resolving relative to REPO_ROOT first (most common case)
            resolved_path = (REPO_ROOT / env_repo_path).resolve()
            if resolved_path.exists() and resolved_path.is_dir():
                print(f"Using ontology repository from environment: {resolved_path.absolute()}")
                return resolved_path.absolute()
            # Try resolving relative to current working directory
            resolved_path = Path(env_repo_path).resolve()
            if resolved_path.exists() and resolved_path.is_dir():
                print(f"Using ontology repository from environment: {resolved_path.absolute()}")
                return resolved_path.absolute()
            print(f"Warning: Environment path {env_repo_path} does not exist or is not a directory")
            print(f"  Tried: {(REPO_ROOT / env_repo_path).resolve()}")
            print(f"  Tried: {Path(env_repo_path).resolve()}")
        else:
            resolved_path = Path(env_repo_path).resolve()
            if resolved_path.exists() and resolved_path.is_dir():
                print(f"Using ontology repository from environment: {resolved_path.absolute()}")
                return resolved_path.absolute()
            print(f"Warning: Environment path {env_repo_path} does not exist or is not a directory")
    
    # Check if ontology repo is in parent directory (GitHub Actions structure)
    parent_repo = (REPO_ROOT.parent / "ontology-repo").resolve()
    if parent_repo.exists() and parent_repo.is_dir():
        print(f"Using ontology repository from parent directory: {parent_repo.absolute()}")
        return parent_repo.absolute()
    
    # Otherwise, clone the repository
    repo_path = (REPO_ROOT / ONTOLOGY_REPO_DIR).resolve()
    
    if repo_path.exists():
        print(f"Repository already exists at {repo_path.absolute()}, updating...")
        run_command(["git", "pull"], cwd=repo_path)
    else:
        print(f"Cloning ontology repository from {MAIN_REPO_URL}...")
        run_command(["git", "clone", MAIN_REPO_URL, str(repo_path)])
    
    return repo_path.absolute()


def find_ontology_files(repo_path: Path) -> List[Path]:
    """Find all ontology .ttl files, excluding shapes files but including them separately."""
    ontology_files = []
    shapes_files = []
    
    # Debug: Check if repo_path exists and list its contents
    if not repo_path.exists():
        print(f"Error: Repository path does not exist: {repo_path}")
        print(f"Current working directory: {os.getcwd()}")
        print(f"REPO_ROOT: {REPO_ROOT}")
        return ontology_files, shapes_files
    
    # Prefer the dedicated ontology subdirectory if present
    ontology_dir = (repo_path / "ontology")
    search_base = ontology_dir if ontology_dir.exists() and ontology_dir.is_dir() else repo_path
    print(f"Searching for ontology files in: {search_base.absolute()}")
    
    # List directory contents for debugging
    try:
        dir_contents = list(search_base.iterdir())
        print(f"Directory contains {len(dir_contents)} items")
        if len(dir_contents) <= 10:  # Only print if not too many
            for item in dir_contents:
                print(f"  - {item.name} ({'dir' if item.is_dir() else 'file'})")
    except Exception as e:
        print(f"Warning: Could not list directory contents: {e}")
    
    # Find all .ttl files under the search base
    ttl_files_found = list(search_base.rglob("*.ttl"))
    print(f"Found {len(ttl_files_found)} total .ttl files")
    
    for ttl_file in ttl_files_found:
        # Skip example files (examples_knowledge_graphs directory and legacy examples/ directory)
        if "examples" in str(ttl_file):
            continue
        
        # Skip files in hidden directories
        if any(part.startswith('.') for part in ttl_file.parts):
            continue
        
        # Separate ontology files from shapes files
        if "-shapes.ttl" in ttl_file.name:
            shapes_files.append(ttl_file)
        else:
            ontology_files.append(ttl_file)
    
    print(f"Found {len(ontology_files)} ontology files and {len(shapes_files)} shapes files")
    if ontology_files:
        print("Ontology files:")
        for f in ontology_files[:10]:  # Show first 10
            print(f"  - {f.relative_to(search_base)}")
        if len(ontology_files) > 10:
            print(f"  ... and {len(ontology_files) - 10} more")
    
    return ontology_files, shapes_files


def bind_common_prefixes(graph: Graph) -> None:
    """Bind common prefixes as a safety net when parsing ontology files.
    
    This function pre-binds prefixes to prevent "prefix not bound" errors
    as a fallback. Since ontology files should now properly declare their
    prefixes, this is primarily a safety mechanism. The namespace URIs
    are inferred from common patterns and can be adjusted if needed.
    """
    # Base namespace pattern - adjust if your actual namespace differs
    # Common patterns: "https://ontology.projectvic.org/", "http://ontology.projectvic.org/", etc.
    base_ns = "https://ontology.projectvic.org/"
    
    # Map of prefix names to namespace URIs
    # Note: Since ontology files now use cacontology-* prefixes and should
    # properly declare them, this is mainly a safety net. Update these
    # if you encounter any remaining "prefix not bound" errors.
    # The actual prefixes used in files may differ - this list covers
    # common patterns that might be encountered.
    common_prefixes = {
        # Legacy icac-* prefixes (kept as fallback for any remaining old files)
        # These map to the new CACOntology namespace (cacontology-*)
        "icac-ai": f"{base_ns}cacontology-ai#",
        "icac-asset-forfeiture": f"{base_ns}cacontology-asset-forfeiture#",
        "icac-athletic": f"{base_ns}cacontology-athletic#",
        "icac-case": f"{base_ns}cacontology-case-management#",
        "icac-custodial": f"{base_ns}cacontology-custodial#",
        "icac-detection": f"{base_ns}cacontology-detection#",
        "icac-educational": f"{base_ns}cacontology-educational-exploitation#",
        "icac-enterprises": f"{base_ns}cacontology-extremist-enterprises#",
        "icac-forensics": f"{base_ns}cacontology-forensics#",
        "icac-grooming": f"{base_ns}cacontology-grooming#",
        "icac-strategy": f"{base_ns}cacontology-gufo-integration-strategy#",
        "icac-institutional": f"{base_ns}cacontology-institutional-exploitation#",
        "icac-international": f"{base_ns}cacontology-international#",
        "icac-coord": f"{base_ns}cacontology-investigation-coordination#",
        "icac-corruption": f"{base_ns}cacontology-law-enforcement-corruption#",
        "icac-legal": f"{base_ns}cacontology-legal-harmonization#",
        "icac-multi": f"{base_ns}cacontology-multi-jurisdiction#",
        "icac-partnerships": f"{base_ns}cacontology-partnerships#",
        "icac-physical": f"{base_ns}cacontology-physical-evidence#",
        "icac-infrastructure": f"{base_ns}cacontology-platform-infrastructure#",
        "icac-platforms": f"{base_ns}cacontology-platforms#",
        "icac-prevention": f"{base_ns}cacontology-prevention#",
        "icac-production": f"{base_ns}cacontology-production#",
        "icac-recruitment": f"{base_ns}cacontology-recruitment-networks#",
        "icac-sentencing": f"{base_ns}cacontology-sentencing#",
        "icac-registry": f"{base_ns}cacontology-sex-offender-registry#",
        "icac-trafficking": f"{base_ns}cacontology-sex-trafficking#",
        "icac-sextortion": f"{base_ns}cacontology-sextortion#",
        "icac-specialized": f"{base_ns}cacontology-specialized-units#",
        "icac-abduction": f"{base_ns}cacontology-stranger-abduction#",
        "icac-street": f"{base_ns}cacontology-street-recruitment#",
        "icac-tactical": f"{base_ns}cacontology-tactical#",
        "icac-taskforce": f"{base_ns}cacontology-taskforce#",
        "icac-temporal": f"{base_ns}cacontology-temporal-gufo#",
        "icac-training": f"{base_ns}cacontology-training#",
        "icac-undercover": f"{base_ns}cacontology-undercover#",
        # Add cacontology-* prefixes here if needed (files should declare them, but kept as safety net)
        # All ontology files now use the CACOntology namespace (cacontology-* prefixes)
    }
    
    # Bind each prefix to the graph
    for prefix, namespace in common_prefixes.items():
        graph.bind(prefix, namespace)


def merge_ontologies(ontology_files: List[Path], shapes_files: List[Path], output_file: Path) -> None:
    """Merge ontology and shapes files into a single file using rdflib."""
    print(f"Merging {len(ontology_files)} ontology files and {len(shapes_files)} shapes files...")

    merged_graph = Graph()
    
    # Pre-bind common prefixes to avoid "not bound" errors
    bind_common_prefixes(merged_graph)

    # First pass: Load files that parse successfully to collect their prefix bindings
    successful_files = []
    failed_files = []
    
    for ontology_file in sorted(ontology_files):
        print(f"  Loading: {ontology_file.name}")
        try:
            g = Graph()
            # Copy existing prefix bindings from merged_graph
            for prefix, namespace in merged_graph.namespaces():
                g.bind(prefix, namespace)
            g.parse(str(ontology_file), format="turtle")
            # Copy any new prefix bindings back to merged_graph
            for prefix, namespace in g.namespaces():
                merged_graph.bind(prefix, namespace)
            merged_graph += g
            successful_files.append(ontology_file)
        except Exception as e:
            print(f"  Warning: Failed to parse {ontology_file.name}: {e}")
            failed_files.append((ontology_file, e))

    # Second pass: Try failed files again now that we have more prefix bindings
    if failed_files:
        print(f"  Retrying {len(failed_files)} files that failed initially...")
        for ontology_file, original_error in failed_files:
            print(f"  Retrying: {ontology_file.name}")
            try:
                g = Graph()
                # Copy all prefix bindings from merged_graph
                for prefix, namespace in merged_graph.namespaces():
                    g.bind(prefix, namespace)
                g.parse(str(ontology_file), format="turtle")
                # Copy any new prefix bindings back to merged_graph
                for prefix, namespace in g.namespaces():
                    merged_graph.bind(prefix, namespace)
                merged_graph += g
                successful_files.append(ontology_file)
                print(f"  Successfully loaded {ontology_file.name} on retry")
            except Exception as e:
                print(f"  Warning: Still failed to parse {ontology_file.name}: {e}")

    # Merge shapes files
    for shapes_file in sorted(shapes_files):
        print(f"  Loading shapes: {shapes_file.name}")
        try:
            g = Graph()
            # Copy existing prefix bindings from merged_graph
            for prefix, namespace in merged_graph.namespaces():
                g.bind(prefix, namespace)
            g.parse(str(shapes_file), format="turtle")
            # Copy any new prefix bindings back to merged_graph
            for prefix, namespace in g.namespaces():
                merged_graph.bind(prefix, namespace)
            merged_graph += g
        except Exception as e:
            print(f"  Warning: Failed to parse shapes file {shapes_file.name}: {e}")
            continue

    print(f"Writing merged ontology to {output_file}...")
    merged_graph.serialize(str(output_file), format="turtle")
    print(f"Merged ontology contains {len(merged_graph)} triples")
    print(f"Successfully loaded {len(successful_files)}/{len(ontology_files)} ontology files")


def generate_documentation(merged_ontology: Path, output_dir: Path) -> None:
    """Generate documentation using Ontospy."""
    print(f"Generating documentation with Ontospy...")

    # Ensure output directory is empty to avoid interactive overwrite prompts
    if output_dir.exists():
        try:
            # If not empty, clear it to prevent ontospy from prompting
            if any(output_dir.iterdir()):
                print(f"Output directory {output_dir} exists and is not empty; clearing...")
                shutil.rmtree(output_dir)
        except Exception as e:
            print(f"Warning: Failed to inspect or clear output directory {output_dir}: {e}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if ontospy is available as a Python module first
    try:
        import ontospy
        print(f"Ontospy module found (version check skipped)")
    except ImportError:
        print("Error: ontospy Python module not found.")
        print("Please install dependencies with: pip install -r requirements.txt")
        sys.exit(1)
    
    # First try programmatic generation to avoid interactive CLI prompts
    try:
        from ontospy import Ontospy as OntospyModel
        visualizer_cls = None
        try:
            # Newer multi-page visualizer
            from ontodocs.viz.viz_html_multi import HTMLVisualizerMulti as Visualizer
            visualizer_cls = Visualizer
            print("Using ontodocs.viz.viz_html_multi.HTMLVisualizerMulti")
        except Exception:
            try:
                # Fallback single/multi visualizer module
                from ontodocs.viz.viz_html import HTMLVisualizer as Visualizer
                visualizer_cls = Visualizer
                print("Using ontodocs.viz.viz_html.HTMLVisualizer")
            except Exception:
                visualizer_cls = None

        if visualizer_cls is not None:
            model = OntospyModel(str(merged_ontology))
            viz = visualizer_cls(model)
            # Some visualizers use build(); others expose build() with output_path
            try:
                viz.build(output_path=str(output_dir))
            except TypeError:
                # Older signature: build(dirpath)
                viz.build(str(output_dir))
            print(f"Documentation generated in {output_dir} (programmatic API)")
            return
        else:
            print("ontodocs visualizer modules not available; falling back to CLI")
    except Exception as e:
        print(f"Programmatic Ontospy generation failed or unavailable: {e}")

    # Check if ontospy command-line tool is available
    ontospy_cmd_available = False
    try:
        result = run_command(["ontospy", "--help"], check=False)
        if result.returncode == 0 or "usage" in result.stdout.lower() or "usage" in result.stderr.lower():
            ontospy_cmd_available = True
    except FileNotFoundError:
        pass
    
    # Try alternative command formats
    if not ontospy_cmd_available:
        try:
            result = run_command(["python", "-m", "ontospy", "--help"], check=False)
            if result.returncode == 0 or "usage" in result.stdout.lower() or "usage" in result.stderr.lower():
                ontospy_cmd_available = True
                ontospy_cmd = ["python", "-m", "ontospy"]
            else:
                ontospy_cmd = ["ontospy"]
        except FileNotFoundError:
            ontospy_cmd = ["ontospy"]
    else:
        ontospy_cmd = ["ontospy"]
    
    if not ontospy_cmd_available:
        print("Warning: Could not verify ontospy command-line tool, but module is installed.")
        print("Attempting to use ontospy command anyway...")
    
    # Generate documentation using Ontospy
    # Ontospy gendocs command: ontospy gendocs <ontology_file> -o <output_dir>
    cmd = ontospy_cmd + [
        "gendocs",
        str(merged_ontology),
        "-o",
        str(output_dir)
    ]

    # Try to answer common interactive prompts: 2 (Html: multi page), 0 (default theme)
    seeded_input = "2\n0\n"
    try:
        print(f"Running: {' '.join(cmd)}")
        result = run_command(cmd, check=False, input_text=seeded_input, timeout=ONTOSPY_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        print("Warning: Ontospy gendocs timed out. Checking if docs were generated...")
        # If docs exist despite timeout, accept success
        if output_dir.exists() and any(output_dir.iterdir()):
            print(f"Documentation appears to be generated in {output_dir} despite timeout.")
            return
        print("Retrying with python -m ontospy...")
        alt_cmd = ["python", "-m", "ontospy", "gendocs", str(merged_ontology), "-o", str(output_dir)]
        try:
            result = run_command(alt_cmd, check=False, input_text=seeded_input, timeout=ONTOSPY_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            print("Error: Ontospy gendocs repeatedly timed out. Checking docs directory one last time...")
            if output_dir.exists() and any(output_dir.iterdir()):
                print(f"Documentation appears to be generated in {output_dir} despite repeated timeouts.")
                return
            sys.exit(1)

    if result.returncode != 0:
        print(f"Error output: {result.stderr}")
        print(f"Standard output: {result.stdout}")

        # Try alternative: python -m ontospy gendocs (if not already tried)
        if ontospy_cmd == ["ontospy"]:
            print("Trying alternative: python -m ontospy gendocs...")
            alt_cmd = ["python", "-m", "ontospy", "gendocs", str(merged_ontology), "-o", str(output_dir)]
            result = run_command(alt_cmd, check=False, input_text=seeded_input, timeout=ONTOSPY_TIMEOUT_SECONDS)
            if result.returncode == 0:
                print(f"Documentation generated in {output_dir}")
                return
            # If non-zero but docs exist, accept success
            if output_dir.exists() and any(output_dir.iterdir()):
                print(f"Ontospy returned non-zero but documentation exists in {output_dir}; proceeding.")
                return

        print(f"Error: Ontospy command failed with return code {result.returncode}")
        print("Please ensure ontospy is properly installed: pip install -r requirements.txt")
        # As a last resort, if docs exist, consider it success
        if output_dir.exists() and any(output_dir.iterdir()):
            print(f"Proceeding as docs exist in {output_dir}.")
            return
        sys.exit(1)
    
    print(f"Documentation generated in {output_dir}")


def create_index_html(output_dir: Path) -> None:
    """Create an index.html file that redirects to the main documentation entry point.
    
    GitHub Pages requires an index.html at the root to serve the homepage.
    This function detects the primary entry point (preferring entities.html)
    and creates a redirect page.
    """
    print("Creating index.html...")
    
    if not output_dir.exists():
        print(f"Warning: Output directory {output_dir} does not exist")
        return
    
    # Priority order for main entry points based on README structure
    preferred_files = ["entities.html", "classes.html", "index.html"]
    
    # Find all HTML files in the output directory
    html_files = [f for f in output_dir.iterdir() if f.is_file() and f.suffix == ".html"]
    
    if not html_files:
        print("Warning: No HTML files found in output directory")
        return
    
    # Determine the target file
    target_file = None
    
    # First, try preferred files
    for preferred in preferred_files:
        candidate = output_dir / preferred
        if candidate.exists() and candidate.is_file() and candidate.suffix == ".html":
            target_file = preferred
            break
    
    # If no preferred file found, use the first HTML file (excluding index.html if it exists)
    if target_file is None:
        for html_file in html_files:
            if html_file.name != "index.html":
                target_file = html_file.name
                break
    
    if target_file is None:
        print("Warning: Could not determine target file for index.html redirect")
        return
    
    # Create index.html with meta refresh redirect
    index_content = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="0; url={target_file}">
    <title>CAC Ontology Documentation</title>
    <script>
        // Immediate redirect for better compatibility
        window.location.replace("{target_file}");
    </script>
</head>
<body>
    <p>If you are not redirected automatically, <a href="{target_file}">click here</a>.</p>
</body>
</html>
"""
    
    index_path = output_dir / "index.html"
    try:
        index_path.write_text(index_content, encoding="utf-8")
        print(f"Created index.html redirecting to {target_file}")
    except Exception as e:
        print(f"Error creating index.html: {e}")


def main():
    """Main documentation generation workflow."""
    print("=" * 60)
    print("CAC Ontology Documentation Generator")
    print("=" * 60)
    
    # Change to repository root
    os.chdir(REPO_ROOT)
    
    # Clone/fetch ontology repository
    repo_path = clone_ontology_repo()
    
    # Find all ontology files
    ontology_files, shapes_files = find_ontology_files(repo_path)
    
    if not ontology_files:
        print("Error: No ontology files found!")
        sys.exit(1)
    
    # Create temporary directory for merged ontology
    temp_ontology = Path(TEMP_DIR) / "merged_ontology.ttl"
    
    # Merge all ontologies
    merge_ontologies(ontology_files, shapes_files, temp_ontology)
    
    # Generate documentation
    output_dir = REPO_ROOT / OUTPUT_DIR
    generate_documentation(temp_ontology, output_dir)
    
    # Create index.html for GitHub Pages
    create_index_html(output_dir)
    
    # Cleanup
    print(f"Cleaning up temporary files...")
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    
    print("=" * 60)
    print("Documentation generation complete!")
    print(f"Documentation available at: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()

