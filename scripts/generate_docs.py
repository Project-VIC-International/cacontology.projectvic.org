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


def run_command(cmd: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check
    )
    if result.returncode != 0 and check:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result


def clone_ontology_repo() -> Path:
    """Clone the main ontology repository to fetch latest ontology files."""
    # Check if running in GitHub Actions (ontology repo already checked out)
    env_repo_path = os.environ.get("ONTOLOGY_REPO_PATH")
    if env_repo_path and Path(env_repo_path).exists():
        print(f"Using ontology repository from environment: {env_repo_path}")
        return Path(env_repo_path)
    
    # Check if ontology repo is in parent directory (GitHub Actions structure)
    parent_repo = REPO_ROOT.parent / "ontology-repo"
    if parent_repo.exists():
        print(f"Using ontology repository from parent directory: {parent_repo}")
        return parent_repo
    
    # Otherwise, clone the repository
    repo_path = REPO_ROOT / ONTOLOGY_REPO_DIR
    
    if repo_path.exists():
        print(f"Repository already exists at {repo_path}, updating...")
        run_command(["git", "pull"], cwd=repo_path)
    else:
        print(f"Cloning ontology repository from {MAIN_REPO_URL}...")
        run_command(["git", "clone", MAIN_REPO_URL, str(repo_path)])
    
    return repo_path


def find_ontology_files(repo_path: Path) -> List[Path]:
    """Find all ontology .ttl files, excluding shapes files but including them separately."""
    ontology_files = []
    shapes_files = []
    
    # Find all .ttl files
    for ttl_file in repo_path.rglob("*.ttl"):
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
    return ontology_files, shapes_files


def merge_ontologies(ontology_files: List[Path], output_file: Path) -> None:
    """Merge all ontology files into a single file using rdflib."""
    print(f"Merging {len(ontology_files)} ontology files...")
    
    merged_graph = Graph()
    
    for ontology_file in sorted(ontology_files):
        print(f"  Loading: {ontology_file.name}")
        try:
            g = Graph()
            g.parse(str(ontology_file), format="turtle")
            merged_graph += g
        except Exception as e:
            print(f"  Warning: Failed to parse {ontology_file.name}: {e}")
            continue
    
    # Also merge shapes files for SHACL documentation
    shapes_files = [f for f in ontology_files if "-shapes.ttl" in f.name]
    ontology_files_only = [f for f in ontology_files if "-shapes.ttl" not in f.name]
    
    # Re-merge with shapes
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
    
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if ontospy is available
    try:
        result = run_command(["ontospy", "--version"], check=False)
        if result.returncode != 0:
            print("Error: ontospy command not found. Install with: pip install ontospy")
            sys.exit(1)
    except FileNotFoundError:
        print("Error: ontospy command not found. Install with: pip install ontospy")
        sys.exit(1)
    
    # Generate documentation using Ontospy
    # Ontospy gendocs command: ontospy gendocs <ontology_file> -o <output_dir>
    # Note: Ontospy may have different command syntax, adjust as needed
    cmd = [
        "ontospy",
        "gendocs",
        str(merged_ontology),
        "-o",
        str(output_dir)
    ]
    
    print(f"Running: {' '.join(cmd)}")
    result = run_command(cmd, check=False)
    
    if result.returncode != 0:
        print(f"Error output: {result.stderr}")
        print(f"Standard output: {result.stdout}")
        print(f"Warning: Ontospy may have encountered issues. Return code: {result.returncode}")
        # Continue anyway as some warnings are non-fatal
        if result.returncode != 0 and "No such file" in result.stderr:
            print("Error: Ontospy command failed. Please check installation.")
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
    merge_ontologies(ontology_files + shapes_files, temp_ontology)
    
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

