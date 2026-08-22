/** The provider answers in codes; a person reads names.
 *
 * The backend normalises whatever a transcription server said into the code
 * that server would accept back (`english` -> `en`), which is the right thing
 * to send and the wrong thing to show. The browser already knows every name in
 * every language it renders the interface in, so nothing here needs a table.
 */
export function displayLanguage(code: string | null | undefined, locale: string): string | null {
  if (!code) return null;
  try {
    // `fallback: "code"` hands back the input for anything it does not know --
    // exactly what we want for a language the backend passed through untouched.
    return new Intl.DisplayNames([locale], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}
