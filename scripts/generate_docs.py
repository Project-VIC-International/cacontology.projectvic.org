#!/usr/bin/env python3
import os
import re
import json
import sys
import shutil
import subprocess
import gzip
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple
from xml.etree.ElementTree import Element, SubElement, ElementTree

# Check if rdflib is installed
try:
    import rdflib
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF, RDFS, OWL
except ImportError:
    print("Error: rdflib is not installed. Please run 'pip install rdflib'")
    sys.exit(1)

# Check if ontospy is installed
try:
    import ontospy
    from ontospy.gendocs.viz.viz_html_multi import KompleteViz as HTMLVisualizer
except ImportError:
    print("Error: ontospy is not installed. Please run 'pip install ontospy'")
    sys.exit(1)

# Configuration
REPO_ROOT = Path(__file__).parent.parent
ONTOLOGY_DIR = "ontology_repo/ontology"
SHAPES_DIR = "ontology_repo/shapes"
OUTPUT_DIR = "docs"
TEMP_DIR = "temp_build"

# Site configuration
SITE_BASE_URL = "https://cacontology.projectvic.org"

# Namespaces
CACON = Namespace("https://cacontology.projectvic.org#")

def clone_ontology_repo():
    """Clone or update the ontology repository."""
    ontology_repo_path = REPO_ROOT / "ontology_repo"
    
    if ontology_repo_path.exists():
        print(f"Ontology repository found at {ontology_repo_path}")
        # Check if it's a git repo and pull
        if (ontology_repo_path / ".git").exists():
            print("Updating ontology repository...")
            try:
                subprocess.run(["git", "-C", str(ontology_repo_path), "pull"], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to update ontology repo: {e}")
    else:
        print("Cloning ontology repository...")
        try:
            subprocess.run([
                "git", "clone", 
                "https://github.com/Project-VIC-International/CAC-Ontology.git", 
                str(ontology_repo_path)
            ], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error cloning ontology repo: {e}")
            sys.exit(1)
            
    return ontology_repo_path

def find_ontology_files(base_dir: Path) -> Tuple[List[Path], List[Path]]:
    """Recursively find all .ttl files in the ontology and shapes directories."""
    ontology_files = []
    shapes_files = []
    
    base_ontology = REPO_ROOT / ONTOLOGY_DIR
    base_shapes = REPO_ROOT / SHAPES_DIR
    
    if base_ontology.exists():
        ontology_files = list(base_ontology.rglob("*.ttl"))
    else:
        print(f"Warning: Ontology directory {base_ontology} not found")
        
    if base_shapes.exists():
        shapes_files = list(base_shapes.rglob("*.ttl"))
    else:
        print(f"Warning: Shapes directory {base_shapes} not found")
        
    print(f"Found {len(ontology_files)} ontology files and {len(shapes_files)} shapes files")
    return ontology_files, shapes_files

def merge_ontologies(ontology_files: List[Path], shapes_files: List[Path], output_file: Path) -> Graph:
    """Merge ontology and shapes files into a single file using rdflib."""
    print("Merging ontology files...")
    
    # Create output directory if it doesn't exist
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    merged_graph = Graph()
    
    # Track successful loads
    successful_files = []
    failed_files = []
    
    all_files = ontology_files + shapes_files
    
    for file_path in all_files:
        try:
            # Use rdflib to parse and add to the graph
            merged_graph.parse(str(file_path), format="turtle")
            successful_files.append(file_path)
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            failed_files.append(file_path)
            
    # Serialize the merged graph to the output file
    print(f"Writing merged ontology to {output_file}...")
    merged_graph.serialize(str(output_file), format="turtle")
    print(f"Merged ontology contains {len(merged_graph)} triples")
    print(f"Successfully loaded {len(successful_files)}/{len(ontology_files)} ontology files")
    return merged_graph

def get_ontology_version(graph: Graph) -> str:
    """Extract version information from the ontology graph."""
    # Try owl:versionInfo first
    for s, p, o in graph.triples((None, OWL.versionInfo, None)):
        return str(o)
        
    # Try owl:versionIRI
    for s, p, o in graph.triples((None, OWL.versionIRI, None)):
        # Extract version from IRI (e.g. .../2.1.0)
        iri = str(o)
        if "/" in iri:
            return iri.split("/")[-1]
        return iri
        
    return ""

def generate_documentation(ontology_file: Path, output_dir: Path):
    """Generate HTML documentation using Ontospy."""
    print(f"Generating documentation for {ontology_file}...")
    
    # Load the ontology with Ontospy
    print("Loading ontology into Ontospy...")
    onto = ontospy.Ontospy(str(ontology_file), verbose=True)
    
    # Generate documentation
    print(f"Building HTML documentation in {output_dir}...")
    v = HTMLVisualizer(onto)
    
    # Ontospy generates into a subdirectory, we want it in output_dir
    # So we generate to a temp dir then move
    temp_docs = Path(TEMP_DIR) / "docs"
    if temp_docs.exists():
        shutil.rmtree(temp_docs)
    
    v.build(str(temp_docs))
    
    # Move files to final destination
    if output_dir.exists():
        # Clean existing docs but keep CNAME and .git if they exist
        for item in output_dir.glob("*"):
            if item.name not in [".git", "CNAME", ".nojekyll"]:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        
    # Copy generated files
    # The structure is usually temp_docs/index.html etc.
    for item in temp_docs.glob("*"):
        if item.is_dir():
            shutil.copytree(item, output_dir / item.name)
        else:
            shutil.copy2(item, output_dir / item.name)
            
    print(f"Documentation generated in {output_dir}")

def extract_common_resources(output_dir: Path) -> tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """Extract common CSS and JavaScript from HTML files into shared files.
    
    Returns paths to the extracted common CSS and JS files.
    """
    print("Extracting common resources...")
    
    if not output_dir.exists():
        print(f"Warning: Output directory {output_dir} does not exist")
        return None, None, None
    
    html_files = list(output_dir.rglob("*.html"))
    if not html_files:
        print("No HTML files found to extract resources from")
        return None, None, None
    
    # Sort by size to find substantive files first (likely class documentation)
    html_files.sort(key=lambda f: f.stat().st_size, reverse=True)
    
    js_parts = []
    common_css = ""
    
    print(f"Scanning {len(html_files)} files for extractable resources...")
    
    try:
        for file in html_files:
            try:
                content = file.read_text(encoding="utf-8")
                
                # Extract inline CSS (between <style type="text/css"> and </style>)
                if not common_css:
                    css_match = re.search(r'<style[^>]*type=["\']text/css["\'][^>]*>(.*?)</style>', content, re.DOTALL)
                    if css_match:
                        common_css = css_match.group(1).strip()
                
                # Extract common JavaScript (content inside script tags)
                # We'll extract the menu toggle and search scripts
                
                # Menu toggle script
                if not any('menu-toggle' in part for part in js_parts):
                    menu_match = re.search(
                        r'<script[^>]*>(\s*\$\(["\']#menu-toggle["\']\)\.click\(function\(e\).*?)</script>',
                        content,
                        re.DOTALL
                    )
                    if menu_match:
                        js_parts.append(menu_match.group(1).strip())
                
                # Search input script
                if not any('search-input-sidebar' in part for part in js_parts):
                    search_match = re.search(
                        r'<script[^>]*>(\s*\$\(["\']#search-input-sidebar["\']\)\.keyup\(function.*?)</script>',
                        content,
                        re.DOTALL
                    )
                    if search_match:
                        js_parts.append(search_match.group(1).strip())
                
                # If we found everything, we can stop
                if common_css and len(js_parts) >= 2:
                    print(f"Found all resources in {file.name}")
                    break
                    
            except Exception:
                continue
        
        if not common_css and not js_parts:
            print("Could not find common resources in any file")
            return None, None, None
        
        # Create shared resources directory
        shared_dir = output_dir / "static" / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        
        # Write common CSS file
        common_css_file = shared_dir / "common.css"
        if common_css:
            common_css_file.write_text(common_css, encoding="utf-8")
            print(f"  Created {common_css_file.relative_to(output_dir)}")
        else:
            common_css_file = None
        
        # Write common JS file
        common_js_file = shared_dir / "common.js"
        if js_parts:
            # Wrap in document ready to ensure DOM and jQuery are available
            common_js = "$(document).ready(function() {\n" + "\n\n".join(js_parts) + "\n});"
            common_js_file.write_text(common_js, encoding="utf-8")
            print(f"  Created {common_js_file.relative_to(output_dir)}")
        else:
            common_js_file = None
        
        return common_css_file, common_js_file, shared_dir
        
    except Exception as e:
        print(f"Warning: Failed to extract common resources: {e}")
        return None, None, None


def optimize_html_files(output_dir: Path, common_css_file: Optional[Path] = None, common_js_file: Optional[Path] = None, version_info: str = "") -> None:
    """Minify HTML files and replace inline CSS/JS with shared files to reduce size.
    
    Args:
        output_dir: Directory containing HTML files
        common_css_file: Path to shared CSS file (relative to output_dir)
        common_js_file: Path to shared JS file (relative to output_dir)
        version_info: Ontology version string to inject
    """
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
    css_replaced_count = 0
    js_replaced_count = 0
    lazy_loading_added = 0
    
    for html_file in html_files:
        try:
            # Skip if it's the index file we just created for namespaces
            # (although we might want to optimize it too, but let's be safe)
            if html_file.name == "index.html" and html_file.parent != output_dir:
                # Check if it's one of our redirect pages
                # Actually, optimization should be fine for them too
                pass
            
            original_content = html_file.read_text(encoding="utf-8")
            original_size = len(original_content.encode("utf-8"))
            
            optimized_content = original_content
            
            # Calculate relative path from this HTML file to shared resources
            html_file_rel = html_file.relative_to(output_dir)
            html_file_depth = len(html_file_rel.parent.parts) if html_file_rel.parent != Path('.') else 0
            
            # Calculate correct relative path to shared resources
            css_link_relative = None
            js_link_relative = None
            if common_css_file:
                # Calculate relative path from html_file to css_file
                css_file_rel = common_css_file.relative_to(output_dir)
                # Go up from html_file's directory to output_dir, then to css_file
                if html_file_depth > 0:
                    up_path = '../' * html_file_depth
                    css_link_relative = up_path + str(css_file_rel).replace('\\', '/')
                else:
                    css_link_relative = str(css_file_rel).replace('\\', '/')
            
            if common_js_file:
                # Calculate relative path from html_file to js_file
                js_file_rel = common_js_file.relative_to(output_dir)
                # Go up from html_file's directory to output_dir, then to js_file
                if html_file_depth > 0:
                    up_path = '../' * html_file_depth
                    js_link_relative = up_path + str(js_file_rel).replace('\\', '/')
                else:
                    js_link_relative = str(js_file_rel).replace('\\', '/')
            
            # Replace inline CSS with link to shared CSS file
            if css_link_relative:
                # Find and replace inline style block
                css_pattern = r'<style[^>]*type=["\']text/css["\'][^>]*>.*?</style>'
                css_replacement = f'<link rel="stylesheet" href="{css_link_relative}">'
                if re.search(css_pattern, optimized_content, re.DOTALL):
                    optimized_content = re.sub(css_pattern, css_replacement, optimized_content, flags=re.DOTALL)
                    css_replaced_count += 1
            
            # Replace common JavaScript with link to shared JS file
            if js_link_relative:
                # Replace menu toggle script
                menu_script_pattern = r'<script[^>]*>\s*\$\(["\']#menu-toggle["\']\)\.click\(function\(e\).*?</script>'
                if re.search(menu_script_pattern, optimized_content, re.DOTALL):
                    optimized_content = re.sub(menu_script_pattern, '', optimized_content, flags=re.DOTALL)
                    js_replaced_count += 1
                
                # Replace search input script
                search_script_pattern = r'<script[^>]*>\s*\$\(["\']#search-input-sidebar["\']\)\.keyup\(function.*?</script>'
                if re.search(search_script_pattern, optimized_content, re.DOTALL):
                    optimized_content = re.sub(search_script_pattern, '', optimized_content, flags=re.DOTALL)
                
                # Add shared JS file before closing body tag (only once per file)
                if js_link_relative and f'src="{js_link_relative}"' not in optimized_content:
                    # Find the last </script> before </body>
                    body_end_match = re.search(r'(</script>)(\s*</body>)', optimized_content, re.DOTALL)
                    if body_end_match:
                        optimized_content = optimized_content.replace(
                            body_end_match.group(0),
                            f'{body_end_match.group(1)}<script src="{js_link_relative}" defer></script>{body_end_match.group(2)}'
                        )
                    elif '</body>' in optimized_content:
                        # Fallback: insert before </body>
                        optimized_content = optimized_content.replace(
                            '</body>',
                            f'<script src="{js_link_relative}" defer></script>\n</body>'
                        )
            
            # Add lazy loading to images
            # Replace <img> tags without loading attribute to add loading="lazy"
            def add_lazy_loading(match):
                attrs = match.group(1)
                # Don't add if already has loading attribute
                if 'loading=' not in attrs and 'loading' not in attrs:
                    # Add loading="lazy" before the closing >
                    return f'<img{attrs} loading="lazy">'
                return match.group(0)
            
            # Count images before adding lazy loading
            img_tags_before = re.findall(r'<img[^>]*>', optimized_content)
            
            optimized_content = re.sub(r'<img([^>]*?)>', add_lazy_loading, optimized_content)
            
            # Count how many got lazy loading added (compare before/after)
            img_tags_after = re.findall(r'<img[^>]*loading=["\']lazy["\'][^>]*>', optimized_content)
            lazy_loading_added += len(img_tags_after)
            
            # Add defer to non-critical scripts (only if not already present)
            # Defer jQuery and Bootstrap (non-critical for initial render)
            # CRITICAL: Only defer jQuery if common JS extraction succeeded.
            # If extraction failed, inline scripts using jQuery might remain and break if jQuery is deferred.
            def add_defer_if_missing(match):
                attrs = match.group(1)
                if 'defer' not in attrs and 'async' not in attrs:
                    return f'<script{attrs} defer>'
                return match.group(0)
            
            # Inject version information
            if version_info:
                # Create a version banner
                version_html = f'''
                <div style="background-color: #f8f9fa; border-bottom: 1px solid #dee2e6; padding: 8px 20px; font-size: 14px; color: #6c757d; text-align: right;">
                    Ontology Version: <strong>{version_info}</strong>
                </div>
                '''
                # Insert after body tag
                if '<body' in optimized_content:
                    optimized_content = re.sub(r'(<body[^>]*>)', f'\\1{version_html}', optimized_content, count=1)

            # Apply defer to jQuery ONLY if we successfully extracted common JS
            # DISABLED: Deferring jQuery breaks search functionality and other inline scripts
            # if js_link_relative:
            #     optimized_content = re.sub(
            #         r'<script([^>]*src=["\']static/libs/jquery[^"\']*["\'][^>]*)>',
            #         add_defer_if_missing,
            #         optimized_content
            #     )
            
            # Apply defer to Bootstrap
            optimized_content = re.sub(
                r'<script([^>]*src=["\']static/libs/bootstrap[^"\']*["\'][^>]*)>',
                add_defer_if_missing,
                optimized_content
            )
            # Chart.js needs to be loaded synchronously for inline scripts to work
            # Apply defer to IE viewport bug workaround (non-critical)
            optimized_content = re.sub(
                r'<script([^>]*src=["\']static/libs/bootstrap-3_3_7-dist/js/ie10-viewport-bug-workaround\.js["\'][^>]*)>',
                add_defer_if_missing,
                optimized_content
            )
            
            # Basic minification (remove unnecessary whitespace, but preserve structure)
            # This is a conservative approach that won't break HTML
            
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
    
    if optimized_count > 0 or css_replaced_count > 0 or js_replaced_count > 0 or lazy_loading_added > 0:
        total_saved_mb = total_saved / (1024 * 1024)
        total_saved_kb = total_saved / 1024
        print(f"Optimization complete:")
        print(f"  - Optimized {optimized_count} files")
        print(f"  - Replaced {css_replaced_count} inline CSS blocks")
        print(f"  - Replaced {js_replaced_count} inline JS blocks")
        print(f"  - Added lazy loading to {lazy_loading_added} images")
        print(f"  - Saved {total_saved_kb:.2f} KB ({total_saved_mb:.2f} MB)")
    else:
        print("Optimization complete: No improvements found")


def analyze_file_sizes(directory: Path):
    """Analyze file sizes and report largest files."""
    print("Analyzing file sizes...")
    
    files = list(directory.rglob("*"))
    files = [f for f in files if f.is_file()]
    
    if not files:
        return
        
    # Sort by size
    files.sort(key=lambda f: f.stat().st_size, reverse=True)
    
    print("Largest files:")
    for i, file in enumerate(files[:10]):
        size_mb = file.stat().st_size / (1024 * 1024)
        print(f"  {i+1}. {file.relative_to(directory)}: {size_mb:.2f} MB")

def generate_namespace_indices(graph: Graph, output_dir: Path) -> List[Dict[str, str]]:
    """Generate index pages for each namespace module to handle IRI redirects.
    
    This creates directory structures matching the IRI namespaces (e.g. /abduction/)
    and index.html files that redirect fragments (e.g. #StrangerAbduction) to
    the specific documentation file generated by Ontospy.
    
    Returns:
        A master list of all entities with their metadata (iri, label, comment, type, doc_url)
        for use in generating entities.jsonl.
    """
    print("Generating namespace index pages...")
    
    # Base namespace
    base_ns = "https://cacontology.projectvic.org/"
    
    # Build namespace URI to prefix mapping from RDF namespace declarations
    # Ontospy uses these prefixes (e.g., "cacontology-registry") not URL paths (e.g., "sex-offender-registry")
    ns_uri_to_prefix: Dict[str, str] = {}
    for prefix, uri in graph.namespaces():
        uri_str = str(uri)
        prefix_str = str(prefix)
        # Only track CAC ontology namespaces
        if uri_str.startswith(base_ns) or prefix_str.startswith("cacontology"):
            ns_uri_to_prefix[uri_str] = prefix_str
    
    print(f"  Found {len(ns_uri_to_prefix)} CAC ontology namespace prefixes")
    
    # Collect entities by namespace
    ns_entities = {}
    
    # Master list of all entities for entities.jsonl
    all_entities: List[Dict[str, str]] = []
    
    # Helper to get filename
    def get_filename(prefix, local_name, type_prefix):
        # Match Ontospy naming convention: type-prefixlocalname.html (lowercase)
        # e.g. class-cacontology-abductionstrangerabduction.html
        slug = f"{prefix}{local_name}".lower()
        return f"{type_prefix}-{slug}.html"
    
    # Helper to get label from graph (prefer @en)
    def get_label(subject) -> str:
        labels = list(graph.objects(subject, RDFS.label))
        if not labels:
            return ""
        # Prefer English label
        for label in labels:
            if hasattr(label, 'language') and label.language == 'en':
                return str(label)
        return str(labels[0])
    
    # Helper to get comment from graph (prefer @en)
    def get_comment(subject) -> str:
        comments = list(graph.objects(subject, RDFS.comment))
        if not comments:
            return ""
        # Prefer English comment
        for comment in comments:
            if hasattr(comment, 'language') and comment.language == 'en':
                return str(comment)
        return str(comments[0])

    # Iterate all subjects to find Classes and Properties
    count = 0
    # Use set to avoid duplicates (graph.subjects() yields a subject for every triple it is in)
    for subject in set(graph.subjects()):
        if not isinstance(subject, rdflib.URIRef):
            continue
            
        subject_str = str(subject)
        if not subject_str.startswith(base_ns):
            continue
            
        # Check if it's a Class or Property (Concept is SKOS, Shapes are SHACL)
        types = list(graph.objects(subject, RDF.type))
        entity_type = None
        
        if OWL.Class in types or RDFS.Class in types:
            entity_type = "Class"
        elif any(t for t in types if str(t).endswith("Property")):
            entity_type = "Property"
        elif any(str(t) == "http://www.w3.org/2004/02/skos/core#Concept" for t in types):
            entity_type = "Concept"
        elif any(str(t) == "http://www.w3.org/ns/shacl#NodeShape" for t in types):
            entity_type = "Shape"
            
        if not entity_type:
            continue
            
        # Parse namespace and local name
        # e.g. https://cacontology.projectvic.org/abduction#StrangerAbduction
        # namespace part: abduction/ (or empty for core)
        # local name: StrangerAbduction
        
        if "#" in subject_str:
            ns_part, local_name = subject_str.split("#", 1)
            if ns_part.startswith(base_ns):
                module_path = ns_part[len(base_ns):]
                if module_path.endswith("/"):
                    module_path = module_path[:-1]
                
                # Look up the Ontospy prefix from namespace mappings
                # The namespace URI includes the # (e.g., "https://cacontology.projectvic.org/abduction#")
                ns_uri_with_hash = ns_part + "#"
                
                if ns_uri_with_hash in ns_uri_to_prefix:
                    # Use the actual RDF prefix (e.g., "cacontology-registry")
                    ontospy_prefix = ns_uri_to_prefix[ns_uri_with_hash]
                elif ns_part in ns_uri_to_prefix:
                    # Try without hash
                    ontospy_prefix = ns_uri_to_prefix[ns_part]
                else:
                    # Fallback: derive from URL path (may not work for all namespaces)
                    ontospy_prefix = "cacontology"
                    if module_path:
                        ontospy_prefix = f"cacontology-{module_path.replace('/', '-')}"
                
                type_prefix = "class" if entity_type == "Class" else \
                             "prop" if entity_type == "Property" else \
                             "concept" if entity_type == "Concept" else \
                             "shape"
                             
                filename = get_filename(ontospy_prefix, local_name, type_prefix)
                doc_url = f"{SITE_BASE_URL}/{filename}"
                
                # Get label and comment for entity index
                label = get_label(subject)
                comment = get_comment(subject)
                
                if module_path not in ns_entities:
                    ns_entities[module_path] = []
                    
                ns_entities[module_path].append({
                    "id": local_name,
                    "name": local_name,
                    "type": entity_type,
                    "file": filename,
                    "uri": subject_str
                })
                
                # Add to master entity list
                all_entities.append({
                    "iri": subject_str,
                    "type": entity_type,
                    "label": label if label else local_name,
                    "comment": comment,
                    "doc_url": doc_url
                })
                
                count += 1

    print(f"  Found {count} entities across {len(ns_entities)} modules")
    
    # Generate index pages
    for module_path, entities in ns_entities.items():
        if not module_path:
            continue # Skip root, as we already have an index.html
            
        # Create directory
        target_dir = output_dir / module_path
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Create mapping for JS redirect
        redirect_map = {e["id"]: f"../{e['file']}" for e in entities}
        
        # Sort entities by name
        entities.sort(key=lambda x: x["name"])
        
        # Generate index.html
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{module_path.title()} Module - CAC Ontology</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
        .entity-list {{ list-style: none; padding: 0; }}
        .entity-list li {{ margin-bottom: 10px; padding: 10px; background: #f8f9fa; border-radius: 4px; }}
        .type-badge {{ 
            display: inline-block; padding: 2px 8px; border-radius: 12px; 
            font-size: 0.8em; font-weight: bold; margin-right: 10px; color: white;
        }}
        .class-badge {{ background-color: #3498db; }}
        .prop-badge {{ background-color: #27ae60; }}
        .conc-badge {{ background-color: #e67e22; }}
        .shap-badge {{ background-color: #9b59b6; }}
        a {{ color: #2980b9; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .loading {{ text-align: center; margin-top: 50px; font-style: italic; color: #666; display: none; }}
        .back-link {{ display: inline-block; margin-bottom: 20px; font-size: 0.9em; }}
    </style>
    <script>
        // Redirect logic
        var entityMap = {json.dumps(redirect_map)};
        
        function checkRedirect() {{
            var hash = window.location.hash;
            if (hash) {{
                var id = hash.substring(1); // Remove #
                if (entityMap[id]) {{
                    document.getElementById('loading').style.display = 'block';
                    document.getElementById('content').style.display = 'none';
                    // Use replace to avoid adding to history
                    window.location.replace(entityMap[id]);
                }} else {{
                     console.log("No redirect found for " + id);
                }}
            }}
        }}
        
        window.addEventListener('load', checkRedirect);
        window.addEventListener('hashchange', checkRedirect);
    </script>
</head>
<body>
    <div id="loading" class="loading">
        <p>Redirecting to documentation...</p>
    </div>
    <div id="content" class="container">
        <a href="../index.html" class="back-link">← Back to Main Documentation</a>
        <h1>{module_path.title()} Module</h1>
        <p>This is the namespace index for the <code>{module_path}</code> module.</p>
        <p>Select a class or property to view its documentation:</p>
        
        <ul class="entity-list">
            {''.join(f'<li><span class="type-badge {e["type"].lower()[:4]}-badge">{e["type"]}</span><a href="../{e["file"]}">{e["name"]}</a></li>' for e in entities)}
        </ul>
    </div>
</body>
</html>
"""
        try:
            (target_dir / "index.html").write_text(html_content, encoding="utf-8")
            print(f"  Created index for /{module_path} with {len(entities)} entities")
        except Exception as e:
            print(f"  Error writing index for /{module_path}: {e}")
    
    return all_entities


def generate_robots_txt(output_dir: Path) -> None:
    """Generate robots.txt file to allow crawling and point to sitemap."""
    print("Generating robots.txt...")
    
    robots_content = f"""# CAC Ontology Documentation
# https://cacontology.projectvic.org

User-agent: *
Allow: /

Sitemap: {SITE_BASE_URL}/sitemap.xml
"""
    
    robots_file = output_dir / "robots.txt"
    robots_file.write_text(robots_content, encoding="utf-8")
    print(f"  Created {robots_file.relative_to(output_dir.parent)}")


def generate_llms_txt(output_dir: Path, version_info: str = "") -> None:
    """Generate llms.txt file as an AI agent entrypoint."""
    print("Generating llms.txt...")
    
    version_line = f"Ontology Version: {version_info}\n" if version_info else ""
    
    llms_content = f"""# CAC Ontology Documentation (Project VIC International)
# Machine-readable entrypoint for AI agents and web crawlers
{version_line}
Base URL: {SITE_BASE_URL}/

## What is the CAC Ontology?
The Crimes Against Children (CAC) Ontology Family is a community-developed evolving 
standard that provides a structured (ontology-based) specification for representing 
information commonly analyzed and exchanged by people and systems during investigations 
involving digital evidence related to crimes against children.

The power of CAC Ontology is that it provides a common language to support automated 
normalization, combination and validation of varied information sources to facilitate 
analysis and exploration of investigative questions (who, what, when, timeline, where, how, and why). 
In addition to representing tool results, CAC Ontology ensures that analysis results 
can be traced back to their source(s), keeping track of when, where and who used which 
tools to perform investigative actions on data sources.

CAC Ontology extends the Unified Cyber Ontology (UCO), the Cyber-investigation Analysis 
Standard Expression (CASE) Ontology, and the Unified Foundational Ontology (gUFO). 
This powerful combination provides specialized modules for modeling child exploitation 
investigations, operations, legal processes, reporting, offender tradecraft, victim and 
survivor related information, and digital forensics activities with high semantic precision.

## How to find entity documentation
Entity pages follow predictable URL patterns:

- Classes: {SITE_BASE_URL}/class-<slug>.html
- Properties: {SITE_BASE_URL}/prop-<slug>.html
- Shapes: {SITE_BASE_URL}/shape-<slug>.html
- Concepts: {SITE_BASE_URL}/concept-<slug>.html

The <slug> is the lowercase concatenation of the namespace prefix and local name.
Example: The property `forensics#priorityClassification` has the URL:
  {SITE_BASE_URL}/prop-cacontology-forensicspriorityclassification.html

## Key navigation pages (recommended starting points)
- Entities A-Z: {SITE_BASE_URL}/entities-az.html
- Classes tree: {SITE_BASE_URL}/entities-tree-classes.html
- Properties tree: {SITE_BASE_URL}/entities-tree-properties.html
- Shapes tree: {SITE_BASE_URL}/entities-tree-shapes.html
- Concepts tree: {SITE_BASE_URL}/entities-tree-concepts.html
- Statistics: {SITE_BASE_URL}/stats.html

## Machine-friendly artifacts (recommended for bulk lookup)
- Sitemap: {SITE_BASE_URL}/sitemap.xml
- Entity index (JSONL): {SITE_BASE_URL}/entities.jsonl
- Merged ontology (Turtle): {SITE_BASE_URL}/cacontology.ttl
- Merged ontology (Turtle, gzipped): {SITE_BASE_URL}/cacontology.ttl.gz

## Entity index format (entities.jsonl)
Each line is a JSON object with:
- iri: Full IRI of the entity
- type: Class, Property, Concept, or Shape
- label: Human-readable label
- comment: Description/definition
- doc_url: Direct URL to the documentation page

## Notes
- Canonical ontology IRIs use hash fragments (e.g., .../forensics#priorityClassification).
- For human-readable docs, use the HTML pages above.
- The sitemap lists all available HTML documentation pages.
"""
    
    llms_file = output_dir / "llms.txt"
    llms_file.write_text(llms_content, encoding="utf-8")
    print(f"  Created {llms_file.relative_to(output_dir.parent)}")


def generate_entities_jsonl(all_entities: List[Dict[str, str]], output_dir: Path) -> None:
    """Generate entities.jsonl file with one entity per line."""
    print("Generating entities.jsonl...")
    
    jsonl_file = output_dir / "entities.jsonl"
    
    with open(jsonl_file, "w", encoding="utf-8") as f:
        for entity in sorted(all_entities, key=lambda e: e["iri"]):
            f.write(json.dumps(entity, ensure_ascii=False) + "\n")
    
    print(f"  Created {jsonl_file.relative_to(output_dir.parent)} with {len(all_entities)} entities")


def publish_ontology_dump(temp_ontology: Path, output_dir: Path) -> None:
    """Copy the merged ontology to docs/ and create a gzipped version."""
    print("Publishing ontology dump...")
    
    # Copy TTL file
    ttl_dest = output_dir / "cacontology.ttl"
    shutil.copy2(temp_ontology, ttl_dest)
    print(f"  Created {ttl_dest.relative_to(output_dir.parent)}")
    
    # Create gzipped version
    gz_dest = output_dir / "cacontology.ttl.gz"
    with open(temp_ontology, "rb") as f_in:
        with gzip.open(gz_dest, "wb") as f_out:
            f_out.writelines(f_in)
    
    # Report sizes
    ttl_size_mb = ttl_dest.stat().st_size / (1024 * 1024)
    gz_size_mb = gz_dest.stat().st_size / (1024 * 1024)
    print(f"  Created {gz_dest.relative_to(output_dir.parent)}")
    print(f"  TTL size: {ttl_size_mb:.2f} MB, gzipped: {gz_size_mb:.2f} MB")


def generate_sitemap(output_dir: Path) -> None:
    """Generate sitemap.xml from the built docs directory with priority and lastmod."""
    print("Generating sitemap.xml...")
    
    # Current build date in ISO 8601 format for lastmod
    build_date = datetime.now().strftime("%Y-%m-%d")
    
    # Define high-priority pages (hub pages and key entry points)
    high_priority_pages = {
        "index.html": "1.0",
        "entities-az.html": "0.9",
        "entities-tree-classes.html": "0.9",
        "entities-tree-properties.html": "0.9",
        "entities-tree-shapes.html": "0.9",
        "entities-tree-concepts.html": "0.9",
        "stats.html": "0.9",
        "llms.txt": "0.8",
        "entities.jsonl": "0.8",
        "cacontology.ttl": "0.7",
    }
    
    # Collect all URLs with their priorities
    url_entries = []  # List of (url, priority)
    
    # Add HTML pages
    for html_file in output_dir.rglob("*.html"):
        rel_path = html_file.relative_to(output_dir)
        rel_path_str = str(rel_path).replace(os.sep, '/')
        url = f"{SITE_BASE_URL}/{rel_path_str}"
        priority = high_priority_pages.get(rel_path_str, "0.5")
        url_entries.append((url, priority))
    
    # Add key non-HTML files
    for filename in ["llms.txt", "entities.jsonl", "cacontology.ttl"]:
        file_path = output_dir / filename
        if file_path.exists():
            url = f"{SITE_BASE_URL}/{filename}"
            priority = high_priority_pages.get(filename, "0.5")
            url_entries.append((url, priority))
    
    print(f"  Found {len(url_entries)} URLs to include")
    
    # Check if we need to split (sitemap limit is 50,000 URLs)
    if len(url_entries) > 50000:
        print("  WARNING: More than 50,000 URLs - sitemap splitting not yet implemented")
        print("  Truncating to first 50,000 URLs")
        url_entries = url_entries[:50000]
    
    # Generate sitemap XML
    urlset = Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")
    
    for url, priority in sorted(url_entries, key=lambda x: x[0]):
        url_elem = SubElement(urlset, "url")
        
        loc = SubElement(url_elem, "loc")
        loc.text = url
        
        lastmod = SubElement(url_elem, "lastmod")
        lastmod.text = build_date
        
        priority_elem = SubElement(url_elem, "priority")
        priority_elem.text = priority
    
    sitemap_file = output_dir / "sitemap.xml"
    tree = ElementTree(urlset)
    
    # Write with XML declaration
    with open(sitemap_file, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)
    
    sitemap_size_kb = sitemap_file.stat().st_size / 1024
    print(f"  Created {sitemap_file.relative_to(output_dir.parent)} ({sitemap_size_kb:.1f} KB)")


def verify_ai_artifacts(output_dir: Path) -> bool:
    """Verify that all AI/crawler artifacts were generated successfully."""
    print("Verifying AI/crawler artifacts...")
    
    required_files = [
        "robots.txt",
        "llms.txt",
        "entities.jsonl",
        "cacontology.ttl",
        "cacontology.ttl.gz",
        "sitemap.xml"
    ]
    
    all_present = True
    for filename in required_files:
        file_path = output_dir / filename
        if file_path.exists():
            size_kb = file_path.stat().st_size / 1024
            print(f"  ✓ {filename} ({size_kb:.1f} KB)")
        else:
            print(f"  ✗ {filename} - MISSING!")
            all_present = False
    
    if all_present:
        print("  All AI/crawler artifacts verified!")
    else:
        print("  WARNING: Some artifacts are missing!")
    
    return all_present


def validate_iri_resolution(graph: Graph, output_dir: Path) -> Dict[str, List[str]]:
    """Validate that all CAC Ontology IRIs resolve to documentation pages.
    
    This checks that:
    1. All classes have corresponding documentation files
    2. All properties have corresponding documentation files
    3. All namespace index pages exist for namespaces with entities
    4. All hash-based IRIs can resolve via namespace pages
    
    Returns a dictionary with:
    - 'missing_files': List of expected files that don't exist
    - 'missing_namespaces': List of namespaces without index pages
    - 'broken_links': List of broken internal links in HTML files
    """
    print("Validating IRI resolution...")
    
    results: Dict[str, List[str]] = {
        "missing_files": [],
        "missing_namespaces": [],
        "broken_links": [],
        "validated_entities": 0,
        "validated_namespaces": 0
    }
    
    base_ns = "https://cacontology.projectvic.org/"
    
    # Build namespace URI to prefix mapping from RDF namespace declarations
    # (same logic as generate_namespace_indices)
    ns_uri_to_prefix: Dict[str, str] = {}
    for prefix, uri in graph.namespaces():
        uri_str = str(uri)
        prefix_str = str(prefix)
        if uri_str.startswith(base_ns) or prefix_str.startswith("cacontology"):
            ns_uri_to_prefix[uri_str] = prefix_str
    
    # Helper to get expected filename (same logic as generate_namespace_indices)
    def get_expected_filename(prefix: str, local_name: str, type_prefix: str) -> str:
        slug = f"{prefix}{local_name}".lower()
        return f"{type_prefix}-{slug}.html"
    
    # Track namespaces found
    namespaces_found: Set[str] = set()
    
    # Check all CAC Ontology entities
    for subject in set(graph.subjects()):
        if not isinstance(subject, rdflib.URIRef):
            continue
            
        subject_str = str(subject)
        if not subject_str.startswith(base_ns):
            continue
        
        # Determine entity type
        types = list(graph.objects(subject, RDF.type))
        entity_type = None
        
        if OWL.Class in types or RDFS.Class in types:
            entity_type = "Class"
            type_prefix = "class"
        elif any(t for t in types if str(t).endswith("Property")):
            entity_type = "Property"
            type_prefix = "prop"
        elif any(str(t) == "http://www.w3.org/2004/02/skos/core#Concept" for t in types):
            entity_type = "Concept"
            type_prefix = "concept"
        elif any(str(t) == "http://www.w3.org/ns/shacl#NodeShape" for t in types):
            entity_type = "Shape"
            type_prefix = "shape"
        
        if not entity_type:
            continue
        
        # Parse namespace and local name
        if "#" in subject_str:
            ns_part, local_name = subject_str.split("#", 1)
            if ns_part.startswith(base_ns):
                module_path = ns_part[len(base_ns):]
                if module_path.endswith("/"):
                    module_path = module_path[:-1]
                
                # Track namespace
                if module_path:
                    namespaces_found.add(module_path)
                
                # Look up the Ontospy prefix from namespace mappings
                ns_uri_with_hash = ns_part + "#"
                
                if ns_uri_with_hash in ns_uri_to_prefix:
                    ontospy_prefix = ns_uri_to_prefix[ns_uri_with_hash]
                elif ns_part in ns_uri_to_prefix:
                    ontospy_prefix = ns_uri_to_prefix[ns_part]
                else:
                    # Fallback: derive from URL path
                    ontospy_prefix = "cacontology"
                    if module_path:
                        ontospy_prefix = f"cacontology-{module_path.replace('/', '-')}"
                
                expected_file = get_expected_filename(ontospy_prefix, local_name, type_prefix)
                expected_path = output_dir / expected_file
                
                if not expected_path.exists():
                    results["missing_files"].append(f"{subject_str} -> {expected_file}")
                else:
                    results["validated_entities"] += 1
    
    # Check namespace index pages exist
    for namespace in namespaces_found:
        namespace_index = output_dir / namespace / "index.html"
        if namespace_index.exists():
            results["validated_namespaces"] += 1
        else:
            results["missing_namespaces"].append(namespace)
    
    # Validate internal links in HTML files
    html_files = list(output_dir.rglob("*.html"))
    link_pattern = re.compile(r'href=["\']([^"\'#]+\.html)["\']')
    
    for html_file in html_files:
        try:
            content = html_file.read_text(encoding="utf-8")
            links = link_pattern.findall(content)
            
            for link in links:
                # Skip external links
                if link.startswith("http://") or link.startswith("https://"):
                    continue
                
                # Resolve relative path
                if link.startswith("../"):
                    # Relative to parent
                    target_path = html_file.parent.parent / link[3:]
                elif link.startswith("./"):
                    target_path = html_file.parent / link[2:]
                else:
                    target_path = html_file.parent / link
                
                # Normalize path
                try:
                    target_path = target_path.resolve()
                    if not target_path.exists():
                        # Check if it might be in output_dir root
                        alt_path = output_dir / link.replace("../", "")
                        if not alt_path.exists():
                            results["broken_links"].append(
                                f"{html_file.relative_to(output_dir)} -> {link}"
                            )
                except Exception:
                    pass
                    
        except Exception as e:
            print(f"  Warning: Could not validate links in {html_file.name}: {e}")
    
    # Print summary
    print(f"  Validated {results['validated_entities']} entity documentation files")
    print(f"  Validated {results['validated_namespaces']}/{len(namespaces_found)} namespace index pages")
    
    if results["missing_files"]:
        print(f"\n  WARNING: {len(results['missing_files'])} entities missing documentation files:")
        for missing in results["missing_files"][:10]:  # Show first 10
            print(f"    - {missing}")
        if len(results["missing_files"]) > 10:
            print(f"    ... and {len(results['missing_files']) - 10} more")
    
    if results["missing_namespaces"]:
        print(f"\n  WARNING: {len(results['missing_namespaces'])} namespaces missing index pages:")
        for ns in results["missing_namespaces"]:
            print(f"    - /{ns}/")
    
    if results["broken_links"]:
        print(f"\n  WARNING: {len(results['broken_links'])} broken internal links found:")
        for link in results["broken_links"][:10]:  # Show first 10
            print(f"    - {link}")
        if len(results["broken_links"]) > 10:
            print(f"    ... and {len(results['broken_links']) - 10} more")
    
    if not results["missing_files"] and not results["missing_namespaces"] and not results["broken_links"]:
        print("  All IRIs resolve correctly!")
    
    return results


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
    merged_graph = merge_ontologies(ontology_files, shapes_files, temp_ontology)
    
    # Get ontology version
    version_info = get_ontology_version(merged_graph)
    print(f"Detected ontology version: {version_info}")

    # Generate documentation
    output_dir = REPO_ROOT / OUTPUT_DIR
    generate_documentation(temp_ontology, output_dir)
    
    # Generate namespace index pages for IRI resolution
    # Also returns the master entity list for entities.jsonl
    all_entities = generate_namespace_indices(merged_graph, output_dir)
    
    # Extract common CSS and JavaScript into shared files
    common_css_file, common_js_file, shared_dir = extract_common_resources(output_dir)
    
    # Optimize HTML files to reduce size (and replace inline resources with shared files)
    optimize_html_files(output_dir, common_css_file, common_js_file, version_info)
    
    # Generate AI/crawler accessibility artifacts
    print("")
    print("=" * 60)
    print("Generating AI/Crawler Accessibility Artifacts")
    print("=" * 60)
    generate_robots_txt(output_dir)
    generate_llms_txt(output_dir, version_info)
    generate_entities_jsonl(all_entities, output_dir)
    publish_ontology_dump(temp_ontology, output_dir)
    generate_sitemap(output_dir)
    verify_ai_artifacts(output_dir)
    print("=" * 60)
    
    # Validate IRI resolution
    validation_results = validate_iri_resolution(merged_graph, output_dir)
    
    # Analyze file sizes and report potential issues
    analyze_file_sizes(output_dir)
    
    # Check total size and warn if too large for GitHub Pages
    total_size = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
    total_size_gb = total_size / (1024 * 1024 * 1024)
    
    if total_size_gb > 1.0:
        print("")
        print("=" * 60)
        print("CRITICAL WARNING: Documentation size exceeds GitHub Pages limits!")
        print("=" * 60)
        print(f"Total size: {total_size_gb:.2f} GB")
        print("GitHub Pages has a soft limit of 1GB per repository.")
        print("")
        print("The site may not deploy correctly or may experience severe loading issues.")
        print("Consider:")
        print("  - Splitting documentation into multiple repositories")
        print("  - Hosting documentation externally (e.g., AWS S3, Netlify)")
        print("  - Optimizing generated HTML further")
        print("=" * 60)

if __name__ == "__main__":
    main()
