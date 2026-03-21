# CAC Ontology Documentation Site

This repository contains the automation for generating and deploying the CAC Ontology documentation site at [cacontology.projectvic.org](https://cacontology.projectvic.org).

## Overview

The documentation is automatically generated using [Ontospy](https://github.com/lambdamusic/Ontospy) from the ontology files in the main [CAC-Ontology repository](https://github.com/Project-VIC-International/CAC-Ontology). The documentation mirrors the structure and style of the [CASE Ontology documentation site](https://ontology.caseontology.org/documentation/index.html).

### CAC Ontology Architecture (v3.0.0+)

The ontology family uses a three-layer architecture:

1. **Semantic Spine** (`cac-core:` namespace) -- A stable, top-level class hierarchy organized by ontological kind (Entity, EnduringEntity, Event, Situation, Role, Phase). All domain modules anchor to the spine.
2. **Bridge Modules** -- Alignment layers mediating between the spine and external foundational ontologies (gUFO, CASE, UCO).
3. **Domain Modules** (35+) -- Specialized modules organized into six areas: Core Framework, International Coordination, Criminal Activities, Specialized Investigation, Technical Support, and Victim Services & Task Force Management.

Each domain module has a corresponding SHACL shapes module for validation.

## Features

- **Automated Generation**: Documentation regenerates automatically on every push to the main ontology repository
- **Comprehensive Coverage**: Documents all 35+ ontology modules, classes, properties, and SHACL shapes including the semantic spine and bridge modules
- **CASE Ontology Style**: Matches the visual style and navigation structure of the CASE Ontology documentation
- **GitHub Pages Hosting**: Automatically deployed to GitHub Pages with custom domain support
- **IRI Resolution**: Namespace index pages ensure all ontology IRIs resolve to documentation
- **Link Validation**: Automated validation ensures all internal links and IRIs resolve correctly
- **Dependabot Integration**: Automated dependency updates keep the build system secure and current

## Documentation Structure

The generated documentation includes:

- **Entities A-Z**: Alphabetical listing of all ontology entities
- **Classes**: Complete list of all ontology classes with detailed documentation
- **Properties**: All object and datatype properties
- **SKOS Concepts**: Vocabulary concepts defined in the ontology
- **Shapes**: All SHACL validation shapes
- **Statistics**: Ontology metrics and statistics
- **Namespace Index Pages**: Per-module landing pages for IRI resolution

## How It Works

1. **GitHub Actions Workflow**: The `.github/workflows/deploy_docs.yml` workflow triggers on:
   - Push to main branch (for script/config changes)
   - Scheduled checks (daily at 2 AM UTC to detect ontology changes)
   - Manual workflow dispatch

2. **Documentation Generation**: The `scripts/generate_docs.py` script:
   - Fetches the latest ontology files from the main CAC-Ontology repository
   - Merges all ontology modules into a unified ontology
   - Generates comprehensive documentation using Ontospy
   - Creates namespace index pages for IRI resolution
   - Validates that all IRIs resolve to documentation pages
   - Outputs optimized HTML files to the `docs/` directory

3. **Deployment**: Generated documentation is automatically deployed to the `gh-pages` branch and served via GitHub Pages.

4. **Dependency Management**: Dependabot automatically creates pull requests for:
   - Python dependency updates (weekly)
   - GitHub Actions workflow updates (weekly)

## IRI Resolution

The documentation supports IRI resolution for all ontology entities. When someone accesses an IRI like:

```
https://cacontology.projectvic.org/abduction#StrangerAbduction
```

The system:
1. Loads the namespace index page at `/abduction/index.html`
2. JavaScript redirects to the appropriate entity documentation
3. Users see the full documentation for `StrangerAbduction`

This ensures that software using the CAC Ontology can link directly to entity documentation.

## Local Development

### Prerequisites

- Python 3.9+ (recommended: 3.11)
- Git

### Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/Project-VIC-International/cacontology.projectvic.org.git
   cd cacontology.projectvic.org
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Generate documentation locally:
   ```bash
   python scripts/generate_docs.py
   ```

4. View the generated documentation:
   ```bash
   # Open docs/index.html in a web browser
   # Or use a local server:
   python -m http.server 8000 -d docs
   ```

## Repository Structure

```
.
├── .github/
│   ├── dependabot.yml          # Dependabot configuration
│   └── workflows/
│       └── deploy_docs.yml     # GitHub Actions workflow
├── scripts/
│   └── generate_docs.py        # Documentation generation script
├── docs/                       # Generated documentation (gitignored)
├── CNAME                       # Custom domain configuration
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Custom Domain

The documentation is configured to be served at `cacontology.projectvic.org`. The `CNAME` file ensures GitHub Pages serves the content on this custom domain.

To configure the custom domain:
1. Add the `CNAME` file to the repository (already included)
2. Configure DNS settings at projectvic.org to point to GitHub Pages
3. Enable custom domain in GitHub Pages settings

## Dependencies

| Package | Purpose | Version Constraint |
|---------|---------|-------------------|
| **ontospy** | Ontology documentation generator | >=2.1.1 |
| **ontodocs** | Documentation templates | >=1.2.0 |
| **Django** | Template engine (for ontodocs) | >=3.2, <7.0 |
| **rdflib** | RDF processing library | >=7.0.0 |
| **robotframework** | Ontology processing | >=7.0.0 |
| **requests** | HTTP utilities | >=2.31.0 |

> **Note**: Django is constrained to <7.0 for compatibility with ontodocs template tags.

See `requirements.txt` for the complete dependency list.

## Dependency Management

This repository uses [Dependabot](https://docs.github.com/en/code-security/dependabot) for automated dependency management:

- **Python Dependencies**: Checked weekly for updates
- **GitHub Actions**: Checked weekly for updates
- **Security Alerts**: Automatic alerts for vulnerable dependencies

Dependabot creates pull requests for available updates, which are reviewed and merged by maintainers.

## Contributing

To update the documentation generation process:

1. Make changes to the scripts or configuration
2. Test locally using `python scripts/generate_docs.py`
3. Verify the generated documentation in `docs/`
4. Commit and push to the main branch
5. GitHub Actions will automatically regenerate and deploy the documentation

### Reporting Issues

If you find broken links or IRIs that don't resolve:
1. Check the GitHub Actions workflow logs for validation errors
2. Open an issue with the specific IRI or link that's broken
3. Include the expected behavior and actual result

## License

This documentation automation is part of the CAC Ontology project. See the main [CAC-Ontology repository](https://github.com/Project-VIC-International/CAC-Ontology) for license information.
