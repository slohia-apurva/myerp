// The parts of Google Identity Services (accounts.google.com/gsi/client) we use.
declare namespace google.accounts.id {
  function initialize(options: {
    client_id: string;
    callback: (response: { credential: string }) => void;
    ux_mode?: "popup" | "redirect";
  }): void;
  function renderButton(
    parent: HTMLElement,
    options: { theme?: string; size?: string; text?: string; shape?: string; width?: number },
  ): void;
  function disableAutoSelect(): void;
}
