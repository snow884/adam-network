Read your memory file `AGENTS.md` first to see which directory URLs you have already submitted Adam Network to.

Search the web (DuckDuckGo) for an AI project directory, MCP server directory, or startup directory that is NOT already listed in `AGENTS.md`.

Navigate to that site, find its submission or registration form, and fill in the input fields using `fill_element` with only the Adam Network project facts listed in your system prompt (name, website, GitHub repo, description, email `adam.ivansky@gmail.com`), looking up any missing details on the GitHub repo page if needed.

If the directory requires account registration or email verification during signup or submission, use your IMAP email tools (`wait_for_verification_email` or `search_verification_emails`) to retrieve the verification link or OTP confirmation code, and navigate to the verification link or enter the verification code to complete verification.

Submit the listing form using `click_element` or `press_key`.

Finally, append a new line to `AGENTS.md` in the format `- YYYY-MM-DD | URL | Status` recording the directory URL, today's date, and status, whether or not the submission succeeded, so it is never attempted again.
