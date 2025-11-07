#!/usr/bin/env python3
"""
ICAC Ontology Documentation Generation Script

This script generates comprehensive documentation for the ICAC Ontology using Ontospy.
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
TEMP_DIR = tempfile.mkdtemp(prefix="icac_docs_")

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
    
    print(f"Searching for ontology files in: {repo_path.absolute()}")
    
    # List directory contents for debugging
    try:
        dir_contents = list(repo_path.iterdir())
        print(f"Directory contains {len(dir_contents)} items")
        if len(dir_contents) <= 10:  # Only print if not too many
            for item in dir_contents:
                print(f"  - {item.name} ({'dir' if item.is_dir() else 'file'})")
    except Exception as e:
        print(f"Warning: Could not list directory contents: {e}")
    
    # Find all .ttl files
    ttl_files_found = list(repo_path.rglob("*.ttl"))
    print(f"Found {len(ttl_files_found)} total .ttl files")
    
    for ttl_file in ttl_files_found:
        # Skip example files
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
            print(f"  - {f.relative_to(repo_path)}")
        if len(ontology_files) > 10:
            print(f"  ... and {len(ontology_files) - 10} more")
    
    return ontology_files, shapes_files


def merge_ontologies(ontology_files: List[Path], shapes_files: List[Path], output_file: Path) -> None:
    """Merge ontology and shapes files into a single file using rdflib."""
    print(f"Merging {len(ontology_files)} ontology files and {len(shapes_files)} shapes files...")

    merged_graph = Graph()

    # Merge ontology (non-shapes) files
    for ontology_file in sorted(ontology_files):
        print(f"  Loading: {ontology_file.name}")
        try:
            g = Graph()
            g.parse(str(ontology_file), format="turtle")
            merged_graph += g
        except Exception as e:
            print(f"  Warning: Failed to parse {ontology_file.name}: {e}")
            continue

    # Merge shapes files
    for shapes_file in sorted(shapes_files):
        print(f"  Loading shapes: {shapes_file.name}")
        try:
            g = Graph()
            g.parse(str(shapes_file), format="turtle")
            merged_graph += g
        except Exception as e:
            print(f"  Warning: Failed to parse shapes file {shapes_file.name}: {e}")
            continue

    print(f"Writing merged ontology to {output_file}...")
    merged_graph.serialize(str(output_file), format="turtle")
    print(f"Merged ontology contains {len(merged_graph)} triples")


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
        result = run_command(cmd, check=False, input_text=seeded_input, timeout=300)
    except subprocess.TimeoutExpired:
        print("Warning: Ontospy gendocs timed out; retrying with python -m ontospy...")
        alt_cmd = ["python", "-m", "ontospy", "gendocs", str(merged_ontology), "-o", str(output_dir)]
        try:
            result = run_command(alt_cmd, check=False, input_text=seeded_input, timeout=300)
        except subprocess.TimeoutExpired:
            print("Error: Ontospy gendocs repeatedly timed out. Aborting.")
            sys.exit(1)

    if result.returncode != 0:
        print(f"Error output: {result.stderr}")
        print(f"Standard output: {result.stdout}")

        # Try alternative: python -m ontospy gendocs (if not already tried)
        if ontospy_cmd == ["ontospy"]:
            print("Trying alternative: python -m ontospy gendocs...")
            alt_cmd = ["python", "-m", "ontospy", "gendocs", str(merged_ontology), "-o", str(output_dir)]
            result = run_command(alt_cmd, check=False, input_text=seeded_input, timeout=300)
            if result.returncode == 0:
                print(f"Documentation generated in {output_dir}")
                return

        print(f"Error: Ontospy command failed with return code {result.returncode}")
        print("Please ensure ontospy is properly installed: pip install -r requirements.txt")
        sys.exit(1)
    
    print(f"Documentation generated in {output_dir}")


def main():
    """Main documentation generation workflow."""
    print("=" * 60)
    print("ICAC Ontology Documentation Generator")
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
    
    # Cleanup
    print(f"Cleaning up temporary files...")
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    
    print("=" * 60)
    print("Documentation generation complete!")
    print(f"Documentation available at: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()

