# Arxiv Paper Summarizer

Arxiv Paper Summarizer is a Python script that helps you search for, download, and generate summaries of research papers from the Arxiv platform. It uses OpenAI's GPT-4 to generate summaries of paper abstracts and content, providing an efficient way to explore and understand research papers.

## Features

- Search for research papers on Arxiv using query and filter keywords
- Download papers in PDF format
- Generate summaries for paper abstracts and content
- Output summaries in Markdown or plain text format
- Customize search results by relevance or last updated date
- Download papers using direct PDF URLs
- Save summary visualizations as images (optional)

## Dependencies

- Python 3.6 or higher
- OpenAI API key (get one at https://beta.openai.com/signup/)
- Required Python packages: `openai`, `pandas`, `seaborn`, `matplotlib`, `numpy`, `arxiv`, `pdf2image`, `PyPDF2`, `Pillow`, `argparse`

## Installation

1. Clone this repository to your local machine.
2. Install the required Python packages using the following command:

```
pip install -r requirements.txt
```

3. Set your OpenAI API key as an environment variable:

```
export OPENAI_API_KEY=your_api_key_here
```

Or pass as an argument `api_key`

## Usage

Run the script with command-line arguments to customize your search and summarization process. Use the `-h` flag to see available options:
```
python summarize.py -h
```

## Example Usage
```
python arxiv_paper_summarizer.py --query "ti: reinforcement learning" --key_word "deep reinforcement learning" --filter_keys "reinforcement learning" --max_results 5 --sort "Relevance" --save_image --file_format "md" --summary_prompt_token 1500 --method_prompt_token 1000
```

In this example, the script searches for papers with "reinforcement learning" in the title, uses "deep reinforcement learning" as the key word, filters the results using "reinforcement learning", retrieves a maximum of 5 results sorted by relevance, saves the generated summary images, and outputs the summaries in Markdown format with specified token limits for abstract and content summaries.


## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.