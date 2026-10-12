import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const mockedLoad = jest.fn();
const mockedSave = jest.fn();
const mockedSuccess = jest.fn();
const mockedError = jest.fn();

jest.mock("@/api", () => ({
  useGetGlobalPrivacyPolicyConfigQuery: () => mockedLoad(),
  useUpdateGlobalPrivacyPolicyConfigMutation: () => [mockedSave],
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
jest.mock("react-toastify", () => ({
  toast: { success: (...args: unknown[]) => mockedSuccess(...args), error: (...args: unknown[]) => mockedError(...args) },
}));
jest.mock("@/components", () => ({
  MarkdownEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <textarea aria-label="policy" value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}));
jest.mock("@stustapay/components", () => ({
  Loading: () => <span>Loading</span>,
  Select: ({ value, onChange, options }: { value: string; onChange: (value: string) => void; options: string[] }) => (
    <select aria-label="language" value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => <option key={option}>{option}</option>)}
    </select>
  ),
}));

const { TabGlobalPrivacyPolicy } = require("./TabGlobalPrivacyPolicy");

describe("global privacy policy", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedLoad.mockReturnValue({ data: { privacy_policy_texts: { "de-DE": "Deutsch", "en-US": "English" } } });
    mockedSave.mockReturnValue({ unwrap: () => Promise.resolve() });
  });

  test("keeps both language edits and saves them through the global endpoint", async () => {
    render(<TabGlobalPrivacyPolicy />);
    fireEvent.change(screen.getByLabelText("policy"), { target: { value: "Neuer Text" } });
    fireEvent.change(screen.getByLabelText("language"), { target: { value: "en-US" } });
    expect((screen.getByLabelText("policy") as HTMLTextAreaElement).value).toBe("English");
    fireEvent.change(screen.getByLabelText("policy"), { target: { value: "New text" } });
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    await waitFor(() => expect(mockedSave).toHaveBeenCalledWith({
      globalPrivacyPolicyConfig: { privacy_policy_texts: { "de-DE": "Neuer Text", "en-US": "New text" } },
    }));
    await waitFor(() => expect(mockedSuccess).toHaveBeenCalled());
  });

  test("shows a load failure without an editable form", () => {
    mockedLoad.mockReturnValue({ error: { status: 403 } });
    render(<TabGlobalPrivacyPolicy />);
    expect(screen.getByRole("alert").textContent).toContain("settings.privacyPolicy.loadErrorTitle");
    expect(screen.queryByLabelText("policy")).toBeNull();
  });
});
