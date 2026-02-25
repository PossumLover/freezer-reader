# 🖥️ Mistral OCR App

A Streamlit application that extracts text, structured data, and tables from PDFs and images using the Mistral OCR API.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Set the `MISTRAL_API_KEY` environment variable with your Mistral API key

   ```
   $ export MISTRAL_API_KEY=your_api_key_here
   ```

3. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

### Setting up the API key as a GitHub repository secret

To make the `MISTRAL_API_KEY` available in GitHub Actions workflows (for deployment or CI):

1. Go to your repository on GitHub (e.g. `https://github.com/PossumLover/tuber-tracker`)
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Set the **Name** to `MISTRAL_API_KEY`
5. Set the **Secret** to your Mistral API key (e.g. `123ABC`)
6. Click **Add secret**

The secret will then be available in your GitHub Actions workflows as `${{ secrets.MISTRAL_API_KEY }}`. To pass it as an environment variable to a workflow step:

```yaml
steps:
  - name: Run app
    env:
      MISTRAL_API_KEY: ${{ secrets.MISTRAL_API_KEY }}
    run: streamlit run streamlit_app.py
```
