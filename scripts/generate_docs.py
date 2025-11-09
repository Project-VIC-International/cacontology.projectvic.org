#!/usr/bin/env python3
"""
CAC Ontology Documentation Generation Script

This script generates comprehensive documentation for the CAC Ontology using Ontospy.
It fetches ontology files from the main CAC-Ontology repository, merges all modules,
and generates HTML documentation matching the CASE Ontology documentation style.
"""

import os
import re
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


def analyze_file_sizes(output_dir: Path) -> None:
    """Analyze file sizes and report potential issues."""
    print("Analyzing file sizes...")
    
    if not output_dir.exists():
        print(f"Warning: Output directory {output_dir} does not exist")
        return
    
    # Find all files and their sizes
    file_sizes = []
    total_size = 0
    
    for file_path in output_dir.rglob("*"):
        if file_path.is_file():
            size = file_path.stat().st_size
            file_sizes.append((file_path, size))
            total_size += size
    
    # Sort by size (largest first)
    file_sizes.sort(key=lambda x: x[1], reverse=True)
    
    # Report statistics
    total_mb = total_size / (1024 * 1024)
    print(f"Total documentation size: {total_mb:.2f} MB ({total_size:,} bytes)")
    print(f"Total files: {len(file_sizes)}")
    
    # Report largest files
    print("\nTop 10 largest files:")
    for i, (file_path, size) in enumerate(file_sizes[:10], 1):
        size_mb = size / (1024 * 1024)
        rel_path = file_path.relative_to(output_dir)
        print(f"  {i:2d}. {size_mb:8.2f} MB  {rel_path}")
    
    # Check for problematic large files
    large_files = [(fp, s) for fp, s in file_sizes if s > 5 * 1024 * 1024]  # > 5MB
    if large_files:
        print(f"\n⚠ WARNING: Found {len(large_files)} file(s) larger than 5MB:")
        for file_path, size in large_files:
            size_mb = size / (1024 * 1024)
            rel_path = file_path.relative_to(output_dir)
            print(f"  - {size_mb:.2f} MB: {rel_path}")
        print("  These files may cause browser timeout or memory issues.")
    
    # Check for files exceeding 1MB (GitHub Pages recommendation)
    medium_files = [(fp, s) for fp, s in file_sizes if s > 1 * 1024 * 1024 and s <= 5 * 1024 * 1024]
    if medium_files:
        print(f"\n⚠ Note: Found {len(medium_files)} file(s) between 1MB and 5MB:")
        print("  These files exceed GitHub Pages recommended limit of 1MB per file.")


def optimize_html_files(output_dir: Path) -> None:
    """Minify HTML files to reduce size and improve load times."""
    print("Optimizing HTML files...")
    
    if not output_dir.exists():
        print(f"Warning: Output directory {output_dir} does not exist")
        return
    
    html_files = list(output_dir.rglob("*.html"))
    if not html_files:
        print("No HTML files found to optimize")
        return
    
    print(f"Found {len(html_files)} HTML file(s) to optimize")
    
    total_saved = 0
    optimized_count = 0
    
    for html_file in html_files:
        try:
            # Read original file
            original_content = html_file.read_text(encoding="utf-8")
            original_size = len(original_content.encode("utf-8"))
            
            # Basic minification (remove unnecessary whitespace, but preserve structure)
            # This is a conservative approach that won't break HTML
            optimized_content = original_content
            
            # Remove HTML comments (but preserve conditional comments for IE)
            # Remove standard HTML comments, but be careful with script/style content
            def remove_comments(match):
                content = match.group(0)
                # Don't remove comments inside script or style tags
                if '<script' in content.lower() or '<style' in content.lower():
                    return content
                # Don't remove conditional comments
                if content.strip().startswith('<!--[if') or content.strip().startswith('<![endif]'):
                    return content
                return ''
            
            # Remove comments (simple approach - remove <!-- ... --> but preserve structure)
            # We'll be conservative and only remove standalone comment lines
            lines = optimized_content.split('\n')
            optimized_lines = []
            in_script = False
            in_style = False
            
            for line in lines:
                # Track script/style tags
                if '<script' in line.lower() and '</script>' not in line.lower():
                    in_script = True
                if '</script>' in line.lower():
                    in_script = False
                if '<style' in line.lower() and '</style>' not in line.lower():
                    in_style = True
                if '</style>' in line.lower():
                    in_style = False
                
                # Skip empty lines and lines with only whitespace (but preserve structure)
                stripped = line.strip()
                if not stripped:
                    # Keep minimal whitespace for readability, but reduce multiple blank lines
                    if optimized_lines and optimized_lines[-1].strip():
                        continue  # Skip this blank line if previous wasn't blank
                    else:
                        optimized_lines.append('')
                    continue
                
                # Skip HTML comments (but not in script/style)
                if stripped.startswith('<!--') and stripped.endswith('-->'):
                    # Skip conditional comments
                    if not (stripped.startswith('<!--[if') or stripped.startswith('<![endif]')):
                        if not in_script and not in_style:
                            continue
                
                optimized_lines.append(line)
            
            optimized_content = '\n'.join(optimized_lines)
            
            # Remove trailing whitespace from lines
            optimized_content = '\n'.join(line.rstrip() for line in optimized_content.split('\n'))
            
            # Remove multiple consecutive blank lines (keep max 2)
            import re
            optimized_content = re.sub(r'\n{3,}', '\n\n', optimized_content)
            
            optimized_size = len(optimized_content.encode("utf-8"))
            saved = original_size - optimized_size
            
            if saved > 0:
                html_file.write_text(optimized_content, encoding="utf-8")
                total_saved += saved
                optimized_count += 1
                rel_path = html_file.relative_to(output_dir)
                saved_kb = saved / 1024
                if saved_kb > 10:  # Only report if significant savings
                    print(f"  Optimized {rel_path}: saved {saved_kb:.1f} KB")
        
        except Exception as e:
            print(f"  Warning: Failed to optimize {html_file.relative_to(output_dir)}: {e}")
            continue
    
    if optimized_count > 0:
        total_saved_mb = total_saved / (1024 * 1024)
        total_saved_kb = total_saved / 1024
        print(f"\nOptimization complete:")
        print(f"  - Files optimized: {optimized_count}/{len(html_files)}")
        print(f"  - Total space saved: {total_saved_kb:.1f} KB ({total_saved_mb:.2f} MB)")
    else:
        print("No significant optimization opportunities found")


def create_index_html(output_dir: Path) -> None:
    """Create an index.html file that redirects to the main documentation entry point.
    
    GitHub Pages requires an index.html at the root to serve the homepage.
    This function detects the primary entry point (preferring entities.html)
    and creates a redirect page with improved error handling and loading indicators.
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
    target_file_size = 0
    
    # First, try preferred files
    for preferred in preferred_files:
        candidate = output_dir / preferred
        if candidate.exists() and candidate.is_file() and candidate.suffix == ".html":
            target_file = preferred
            target_file_size = candidate.stat().st_size
            break
    
    # If no preferred file found, use the first HTML file (excluding index.html if it exists)
    if target_file is None:
        for html_file in html_files:
            if html_file.name != "index.html":
                target_file = html_file.name
                target_file_size = html_file.stat().st_size
                break
    
    if target_file is None:
        print("Warning: Could not determine target file for index.html redirect")
        return
    
    # Verify target file is accessible and check its size
    target_path = output_dir / target_file
    if not target_path.exists():
        print(f"Warning: Target file {target_file} does not exist")
        return
    
    target_file_size_mb = target_file_size / (1024 * 1024)
    if target_file_size_mb > 5:
        print(f"Warning: Target file {target_file} is {target_file_size_mb:.2f} MB - may cause loading issues")
    
    # Create index.html with improved redirect, loading indicator, and error handling
    index_content = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="0; url={target_file}">
    <title>CAC Ontology Documentation - Loading...</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }}
        .container {{
            text-align: center;
            max-width: 600px;
        }}
        .spinner {{
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .message {{
            margin: 20px 0;
            font-size: 16px;
            line-height: 1.6;
        }}
        .link {{
            display: inline-block;
            margin-top: 20px;
            padding: 12px 24px;
            background: #3498db;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-weight: 500;
        }}
        .link:hover {{
            background: #2980b9;
        }}
        .error {{
            color: #e74c3c;
            margin-top: 20px;
            padding: 15px;
            background: #ffeaea;
            border-radius: 4px;
            display: none;
        }}
    </style>
    <script>
        (function() {{
            var targetUrl = "{target_file}";
            var redirectAttempted = false;
            var maxWaitTime = 30000; // 30 seconds
            var startTime = Date.now();
            
            function attemptRedirect() {{
                if (redirectAttempted) return;
                redirectAttempted = true;
                
                try {{
                    // Try immediate redirect
                    window.location.replace(targetUrl);
                }} catch (e) {{
                    console.error("Redirect error:", e);
                    showError("Redirect failed. Please use the link below.");
                }}
            }}
            
            function showError(message) {{
                var errorDiv = document.getElementById("error");
                if (errorDiv) {{
                    errorDiv.textContent = message;
                    errorDiv.style.display = "block";
                }}
            }}
            
            function checkTimeout() {{
                var elapsed = Date.now() - startTime;
                if (elapsed > maxWaitTime) {{
                    showError("Page is taking longer than expected to load. The documentation file may be very large. Please use the link below or wait a bit longer.");
                }}
            }}
            
            // Attempt redirect immediately
            attemptRedirect();
            
            // Check for timeout
            setTimeout(checkTimeout, maxWaitTime);
            
            // Fallback: try again after a short delay
            setTimeout(function() {{
                if (window.location.href.indexOf(targetUrl) === -1) {{
                    attemptRedirect();
                }}
            }}, 1000);
        }})();
    </script>
</head>
<body>
    <div class="container">
        <div class="spinner"></div>
        <div class="message">
            <h1>Loading CAC Ontology Documentation</h1>
            <p>Redirecting to the documentation...</p>
            <p style="font-size: 14px; color: #666;">If this page does not redirect automatically, please use the link below.</p>
        </div>
        <a href="{target_file}" class="link">Go to Documentation</a>
        <div id="error" class="error"></div>
    </div>
</body>
</html>
"""
    
    index_path = output_dir / "index.html"
    try:
        index_path.write_text(index_content, encoding="utf-8")
        print(f"Created index.html redirecting to {target_file}")
        if target_file_size_mb > 1:
            print(f"  Note: Target file size is {target_file_size_mb:.2f} MB")
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
    
    # Optimize HTML files to reduce size
    optimize_html_files(output_dir)
    
    # Analyze file sizes and report potential issues
    analyze_file_sizes(output_dir)
    
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

