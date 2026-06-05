# How to Create a Cursor API Key

A Cursor API key (`crsr_...`) lets you authenticate non-interactively — perfect for Docker, CI pipelines, and scripts where you can't run `agent login` in a browser.

---

## Steps

1. Go to **[cursor.com/dashboard/api](https://cursor.com/dashboard/api?section=user-keys#user-api-keys)**
2. Under **User API Keys**, click **Add**
3. Give it any name (e.g. `my-cursorpipe-key`)
4. Set scope to **Admin**
5. Click **Create** — your key (`crsr_...`) is shown **only once**, so copy it now

---

## Using the key with cursorpipe

=== "bash / macOS / Linux / WSL"

    ```bash
    export CURSOR_API_KEY=crsr_your_key_here
    ```

=== "PowerShell (Windows)"

    ```powershell
    $env:CURSOR_API_KEY = "crsr_your_key_here"
    ```

=== "CMD (Windows)"

    ```cmd
    set CURSOR_API_KEY=crsr_your_key_here
    ```

=== ".env file"

    ```bash
    CURSOR_API_KEY=crsr_your_key_here
    ```

    Both `CURSOR_API_KEY` and `CURSORPIPE_API_KEY` are accepted in `.env` files and as OS environment variables.

---

## Can't find the API Keys page?

Cursor occasionally reorganises their dashboard. If the link above doesn't take you to the right place:

1. Log in at [cursor.com](https://cursor.com) and look for **API Keys** or **User API Keys** in the left sidebar
2. Or search the web for **"Cursor API key"**

If the link is broken, **[open an issue](https://github.com/Abhi5h3k/cursorpipe/issues)** or send a PR updating this page — it takes 30 seconds and helps everyone. 🙏
