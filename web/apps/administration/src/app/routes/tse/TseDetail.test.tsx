import * as React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextEncoder =
  TextEncoder;
(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextDecoder =
  TextDecoder;

const mockUseListTsesQuery = jest.fn();
const mockTse = {
  id: 5,
  name: "Managed TSE",
  type: "fiskaly",
  status: "ready",
  fiskaly_profile: null as string | null,
  fiskaly_job_id: 18 as number | null,
  hashalgo: "sha256",
  time_format: "unix",
  public_key: "public-key",
  certificate: "certificate",
  process_data_encoding: "utf8",
};

jest.mock("@/api", () => ({
  selectTseById: () => mockTse,
  useListTsesQuery: (...args: unknown[]) => mockUseListTsesQuery(...args),
}));

jest.mock("@/hooks", () => ({ useCurrentNode: () => ({ currentNode: { id: 12 } }) }));

jest.mock("@/app/routes", () => ({ TseRoutes: { list: () => "/tses", edit: (id: number) => `/tses/${id}/edit` } }));

jest.mock("@/components", () => ({
  DetailLayout: ({ actions, children, title }: {
    actions: Array<{ label: string }>;
    children: React.ReactNode;
    title: string;
  }) => (
    <div>
      <h1>{title}</h1>
      {actions.map((action) => <button key={action.label}>{action.label}</button>)}
      {children}
    </div>
  ),
}));

jest.mock("@stustapay/components", () => ({ Loading: () => <div>loading</div> }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const { MemoryRouter, Route, Routes } = require("react-router-dom");
const { TseDetail } = require("./TseDetail");

describe("TseDetail", () => {
  beforeEach(() => {
    mockUseListTsesQuery.mockImplementation((_arg: unknown, options: { selectFromResult: (data: unknown) => unknown }) =>
      options.selectFromResult({ data: {}, error: undefined })
    );
  });

  it("hides the conventional edit action for a managed Fiskaly TSE", () => {
    render(
      <MemoryRouter initialEntries={["/node/12/tses/5"]}>
        <Routes><Route path="/node/:nodeId/tses/:tseId" element={<TseDetail />} /></Routes>
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "Managed TSE" })).toBeTruthy();
    expect(screen.getByText("tse.fiskalyManaged")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "edit" })).toBeNull();
  });

  it("keeps the edit action for a manually configured Fiskaly profile", () => {
    mockTse.fiskaly_job_id = null;
    mockTse.fiskaly_profile = "manual-profile";
    render(
      <MemoryRouter initialEntries={["/node/12/tses/5"]}>
        <Routes><Route path="/node/:nodeId/tses/:tseId" element={<TseDetail />} /></Routes>
      </MemoryRouter>
    );

    expect(screen.getByRole("button", { name: "edit" })).toBeTruthy();
    expect(screen.getByText("manual-profile")).toBeTruthy();
  });
});
