"""
Code Consolidator Script

Description:
    This script reads all specified source code files (e.g., .py) within an 
    input directory and consolidates them into a single text file. 
    It is specifically designed to prepare codebases for Large Language Models 
    (LLMs) and RAG tools (like NotebookLM) by separating each file's content 
    with a clear header.

Usage from terminal:
    1. Default execution (Reads current directory, saves to ../results):
       python consolidate_code.py
       
    2. Custom execution (Specify input, output, and filename):
       python consolidate_code.py --input ./my_tools --output ./my_results --filename all_code.txt
       
    3. Help menu (View all options):
       python consolidate_code.py -h
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

def get_args() -> argparse.Namespace:
    """Parses command line arguments."""
    # Base directory relative to where this script is located
    script_dir = Path(__file__).parent.resolve()
    
    # Default paths based on your structure: TradingSystem/tools -> TradingSystem/results
    default_input = script_dir
    default_output = script_dir.parent / "results"

    parser = argparse.ArgumentParser(description="Consolidate multiple code files into a single text file.")
    
    parser.add_argument("-i", "--input", type=str, default=str(default_input),
                        help="Input directory containing the files to consolidate.")
    parser.add_argument("-o", "--output", type=str, default=str(default_output),
                        help="Output directory where the consolidated file will be saved.")
    parser.add_argument("-f", "--filename", type=str, default="consolidated_tools.txt",
                        help="Name of the output text file.")
    parser.add_argument("-e", "--extension", type=str, default=".py",
                        help="File extension to filter and consolidate (default: .py).")
    
    return parser.parse_args()

def consolidate_files(input_dir: Path, output_dir: Path, filename: str, extension: str) -> None:
    """
    Reads files from the input directory and writes them to a single output file.
    
    Args:
        input_dir: Directory containing source files.
        output_dir: Directory to save the final file.
        filename: Name of the output file.
        extension: The file extension to target.
    """
    if not input_dir.exists() or not input_dir.is_dir():
        logging.error(f"Input directory does not exist or is not a directory: {input_dir}")
        sys.exit(1)

    # Ensure output directory exists, create if it doesn't
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / filename
    script_name = Path(__file__).name
    
    # Find all files matching the extension
    target_files: List[Path] = list(input_dir.glob(f"*{extension}"))
    
    if not target_files:
        logging.warning(f"No files with extension '{extension}' found in {input_dir}")
        return

    try:
        with open(output_path, 'w', encoding='utf-8') as outfile:
            outfile.write(f"# CONSOLIDATED CODEBASE\n")
            outfile.write(f"# Source Directory: {input_dir}\n")
            outfile.write(f"{'='*50}\n\n")
            
            files_processed = 0
            
            for file_path in target_files:
                # Skip the script itself if it's in the same directory
                if file_path.name == script_name:
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                        
                        # Write visual separator and file name header
                        outfile.write(f"\n\n{'='*50}\n")
                        outfile.write(f"### FILE: {file_path.name}\n")
                        outfile.write(f"{'='*50}\n\n")
                        
                        # Write the actual code
                        outfile.write(content)
                        
                        files_processed += 1
                        logging.info(f"Added: {file_path.name}")
                        
                except Exception as e:
                    logging.error(f"Failed to read file {file_path.name}: {e}")
                    
        logging.info(f"Success! {files_processed} files consolidated into {output_path}")
        
    except Exception as e:
        logging.error(f"Failed to create the consolidated file: {e}")
        sys.exit(1)

def main() -> None:
    """Main execution function."""
    args = get_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    logging.info(f"Starting consolidation process...")
    consolidate_files(
        input_dir=input_path, 
        output_dir=output_path, 
        filename=args.filename, 
        extension=args.extension
    )

if __name__ == "__main__":
    main()