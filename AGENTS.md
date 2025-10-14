# Project Roadmap and Agent Notes

## Overview
This repository will host a tool that scans CBCT data directories, processes the studies with Pylinac using configurable phantoms, and summarizes the analysis results into an XML report. The work will be completed in three incremental tasks, with each step preparing the groundwork for the following one.

## Task Breakdown

### Task 1: Data Discovery and Inventory
- Implement a command-line entry point that accepts a root directory containing CBCT studies.
- Recursively scan the directory tree for CT study folders (e.g., DICOM sets or other supported formats) and gather identifiers such as the study folder path.
- Produce a structured inventory (JSON or similar) listing all discovered studies and metadata needed for later analysis.
- Include logging to help troubleshoot missing or invalid datasets.
- Prepare any reusable utilities that will be needed for later steps (e.g., path resolution helpers).

### Task 2: Batch Pylinac Processing
- Extend the tool to accept a phantom selection (e.g., 503, 504, 600, 604) and apply the appropriate Pylinac analysis workflow to each study from the inventory generated in Task 1.
- Handle failures gracefully (e.g., missing slices, incompatible phantom) while continuing to process the remaining studies.
- Capture all relevant analysis metrics and status details for each study in an intermediate data structure that can be serialized.
- Ensure the interface remains consistent so Task 3 can consume the results without major refactoring.

### Task 3: XML Report Generation
- Transform the aggregated analysis data into a comprehensive XML document.
- Embed the study identifier (e.g., source folder path) alongside all metrics returned by Pylinac.
- Include overall summary statistics (counts of successes/failures, phantom used, runtime info if available).
- Validate the XML output against a simple schema or at least provide clear documentation of the structure.

## Implementation Notes
- Favor modular Python code (functions/modules) so each task can extend the existing structure rather than rewriting logic.
- Add tests as feasible, especially for utility functions and XML generation logic.
- Update this file if priorities change or additional context needs to be recorded for future tasks.
