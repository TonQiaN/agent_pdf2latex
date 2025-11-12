# agent_pdf2latex
This project is to rebuild the function of pdf to latex by using 1.0 version of langchain.

agent_pdf2latex_openai/
├── src/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                 # API keys, paths, constants
│   ├── models/
│   │   ├── __init__.py
│   │   ├── flow_context.py             # FlowContext dataclass
│   │   └── schemas.py                  # JSON response schemas
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── registry.py                 # PromptRegistry class
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── long_prompt.py              # LongPromptMiddleware
│   │   └── output_validation.py        # OutputValidationMiddleware
│   ├── agents/
│   │   ├── __init__.py
│   │   └── pdf_agent.py                # Agent initialization
│   ├── tools/
│   │   ├── __init__.py
│   │   └── file_search.py              # file_search tool
│   ├── services/
│   │   ├── __init__.py
│   │   ├── file_manager.py             # File upload, cache, list, delete
│   │   ├── image_extractor.py          # extract_images_from_pdf
│   │   └── latex_generator.py          # LaTeX file generation & update
│   ├── workflow/
│   │   ├── __init__.py
│   │   ├── steps.py                    # run_classify_step, run_lister_step, etc.
│   │   └── orchestrator.py             # run_complete_workflow
│   └── utils/
│       ├── __init__.py
│       ├── json_parser.py              # extract_json_from_markdown
│       └── display.py                  # show_* functions for notebook
├── notebooks/
│   ├── main.ipynb                      # Main workflow execution
│   ├── demo.ipynb                      # Demo & visualization
│   └── debug.ipynb                     # Debugging & testing
├── tests/
│   ├── __init__.py
│   ├── test_file_manager.py
│   ├── test_workflow.py
│   └── test_prompts.py
├── output/
│   ├── images/                         # Extracted images
│   ├── latex/                          # Generated .tex files
│   └── results/                        # JSON results
├── data/
│   └── cache/
│       └── file_cache_openai.json
├── .env                                # Environment variables
├── requirements.txt
├── README.md
└── setup.py