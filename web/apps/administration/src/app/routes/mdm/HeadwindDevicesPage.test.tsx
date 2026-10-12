import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextEncoder =
  TextEncoder;
(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextDecoder =
  TextDecoder;

let mockedNodeId = 5;
const mockedGrid = jest.fn();
const mockedUpsert = jest.fn();
const mockedTree = {
  id: 0,
  name: "Root",
  event_node_id: null,
  children: [
    {
      id: 5,
      name: "Festival A",
      event_node_id: 5,
      children: [
        { id: 6, name: "Bar", event_node_id: 5, children: [{ id: 7, name: "Front", event_node_id: 5, children: [] }] },
      ],
    },
    { id: 8, name: "Festival B", event_node_id: 8, children: [{ id: 9, name: "Bar", event_node_id: 8, children: [] }] },
  ],
};
const mockedListDevices = jest.fn();
const mockedListMappings = jest.fn();
const mockedListTerminals = jest.fn();

jest.mock("@/hooks", () => ({
  useDebounce: (value: string) => value,
  useCurrentNode: () => ({ currentNode: { id: mockedNodeId, name: "Event" } }),
}));

jest.mock("@/api/mdm", () => ({
  useListHeadwindDevicesQuery: (...args: unknown[]) => mockedListDevices(...args),
  useListHeadwindMappingsQuery: (...args: unknown[]) => mockedListMappings(...args),
  useListTerminalsQuery: (...args: unknown[]) => mockedListTerminals(...args),
  useUpsertHeadwindMappingMutation: () => [mockedUpsert, {}],
  useRefreshHeadwindMappingTokenMutation: () => [jest.fn()],
  useDeleteHeadwindMappingMutation: () => [jest.fn()],
}));

jest.mock("@/api", () => ({
  selectTerminalAll: (data: unknown) => data,
  useNodeTree: () => ({ root: mockedTree }),
  useListTerminalsQuery: (...args: unknown[]) => mockedListTerminals(...args),
}));

jest.mock("@/components", () => ({ ListLayout: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
jest.mock("@stustapay/components", () => ({ Loading: () => null }));
jest.mock("@stustapay/framework", () => ({
  DataGrid: ({
    rows,
    columns,
  }: {
    rows: unknown[];
    columns: { field: string; getActions: (params: unknown) => React.ReactNode }[];
  }) => {
    mockedGrid({ rows, columns });
    return (
      <>
        {rows.map((row, index) => (
          <div key={index}>{columns.find((column) => column.field === "actions")?.getActions({ row })}</div>
        ))}
      </>
    );
  },
  GridActionsCellItem: ({ label, onClick }: { label: string; onClick: () => void }) => (
    <button onClick={onClick}>{label}</button>
  ),
}));
jest.mock("@stustapay/modal-provider", () => ({ useOpenModal: () => jest.fn() }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const { HeadwindDevicesPage } = require("./HeadwindDevicesPage");
const { MemoryRouter, Route, Routes, useLocation } = require("react-router-dom");

const CurrentPath = () => <span data-testid="current-path">{useLocation().pathname}</span>;

describe("HeadwindDevicesPage root guard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedNodeId = 5;
    mockedUpsert.mockReturnValue({ unwrap: () => Promise.resolve() });
    mockedListDevices.mockReturnValue({ data: [{ device: { id: "device-1" } }] });
    mockedListMappings.mockReturnValue({ data: [] });
    mockedListTerminals.mockReturnValue({
      data: [
        { id: 11, name: "POS", node_id: 6 },
        { id: 12, name: "POS", node_id: 9 },
        { id: 13, name: "POS", node_id: 99 },
      ],
    });
  });

  test("redirects an event route to root before calling Headwind or terminal query hooks", () => {
    render(
      <MemoryRouter initialEntries={["/node/5/mdm/devices"]}>
        <Routes>
          <Route path="/node/0/mdm/devices" element={<CurrentPath />} />
          <Route path="/node/:nodeId/mdm/devices" element={<HeadwindDevicesPage />} />
          <Route path="*" element={<CurrentPath />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId("current-path").textContent).toBe("/node/0/mdm/devices");
    expect(mockedListDevices).not.toHaveBeenCalled();
    expect(mockedListMappings).not.toHaveBeenCalled();
    expect(mockedListTerminals).not.toHaveBeenCalled();
  });

  test("distinguishes same-name terminals by their event and node when mapping a device", async () => {
    mockedNodeId = 0;
    render(
      <MemoryRouter>
        <HeadwindDevicesPage />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole("button", { name: "mdm.map" }));
    fireEvent.focus(screen.getByRole("combobox"));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "POS" } });
    expect(screen.getByRole("option", { name: /POS \(#11\).*Festival A \/ Bar/ })).toBeTruthy();
    expect(screen.getByRole("option", { name: /POS \(#13\).*#99/ })).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Festival B" } });
    await waitFor(() => expect(screen.queryByRole("option", { name: /Festival A/ })).toBeNull());
    fireEvent.click(screen.getByRole("option", { name: /POS \(#12\).*Festival B \/ Bar/ }));
    expect((screen.getByRole("combobox") as HTMLInputElement).value).toBe("POS (#12) — Festival B / Bar");
    fireEvent.click(screen.getAllByRole("button", { name: "mdm.map" }).at(-1)!);
    await waitFor(() =>
      expect(mockedUpsert).toHaveBeenCalledWith({
        nodeId: 0,
        payload: expect.objectContaining({ terminal_id: 12, headwind_device_id: "device-1" }),
      })
    );
  });
});

describe("Headwind terminal locations", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedNodeId = 0;
    mockedListDevices.mockReturnValue({ data: [], refetch: jest.fn() });
    mockedListMappings.mockReturnValue({ data: [{ terminal_id: 3, headwind_device_id: "other" }] });
    mockedListTerminals.mockReturnValue({
      data: [
        { id: 2, name: "POS", node_id: 9 },
        { id: 1, name: "POS", node_id: 7 },
        { id: 3, name: "Taken", node_id: 6 },
      ],
    });
    mockedUpsert.mockReturnValue({ unwrap: () => Promise.resolve() });
  });

  test("groups devices into event and nested subnode sections and can restore the flat list", () => {
    mockedListDevices.mockReturnValue({
      data: [
        { device: { id: "a" }, mapping: { node_id: 6, terminal_id: 1 } },
        { device: { id: "b" }, mapping: { node_id: 7, terminal_id: 2 } },
        { device: { id: "c" }, mapping: { node_id: 9, terminal_id: 3 } },
        { device: { id: "d" } },
      ],
      refetch: jest.fn(),
    });
    render(
      <MemoryRouter>
        <HeadwindDevicesPage />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText("mdm.grouping"), { target: { value: "event" } });
    expect(screen.getByRole("button", { name: "Festival A (2)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Festival B (1)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "mdm.notMapped (1)" })).toBeTruthy();
    expect(
      mockedGrid.mock.calls
        .slice(-3)
        .map(([grid]) => grid.rows.length)
        .sort()
    ).toEqual([1, 1, 2]);
    fireEvent.change(screen.getByLabelText("mdm.grouping"), { target: { value: "node" } });
    expect(screen.getByRole("button", { name: "Bar / Front (1)" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Bar (1)" })).toHaveLength(2);
    expect(mockedGrid.mock.calls.slice(-4).map(([grid]) => grid.rows.length)).toEqual([1, 1, 1, 1]);
    fireEvent.change(screen.getByLabelText("mdm.grouping"), { target: { value: "none" } });
    expect(screen.queryByRole("button", { name: "Festival A (2)" })).toBeNull();
    expect(mockedGrid.mock.calls.at(-1)[0].rows).toHaveLength(4);
  });

  test("shows event and full subnode path with fallbacks", () => {
    render(
      <MemoryRouter>
        <HeadwindDevicesPage />
      </MemoryRouter>
    );
    const { columns } = mockedGrid.mock.calls.at(-1)[0];
    const event = columns.find((column: { field: string }) => column.field === "event");
    const node = columns.find((column: { field: string }) => column.field === "node");
    expect(event.valueGetter(null, { mapping: { node_id: 7 } })).toBe("Festival A");
    expect(node.valueGetter(null, { mapping: { node_id: 7 } })).toBe("Bar / Front");
    expect(event.valueGetter(null, { mapping: { node_id: 9 } })).toBe("Festival B");
    expect(node.valueGetter(null, { mapping: { node_id: 5 } })).toBe("mdm.eventRoot");
    expect(event.valueGetter(null, {})).toBe("mdm.notMapped");
    expect(event.valueGetter(null, { mapping: { node_id: 99 } })).toBe("mdm.unknownEvent");
    expect(node.valueGetter(null, { mapping: { node_id: 99 } })).toBe("#99");
  });

  test("groups duplicate names, searches paths and maps the selected terminal", async () => {
    render(
      <MemoryRouter>
        <HeadwindDevicesPage />
      </MemoryRouter>
    );
    const { columns } = mockedGrid.mock.calls.at(-1)[0];
    const actions = columns.find((column: { field: string }) => column.field === "actions");
    render(<>{actions.getActions({ row: { device: { id: "device-1" } } })}</>);
    fireEvent.click(screen.getByRole("button", { name: "mdm.map" }));
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.mouseDown(input);
    expect(screen.getAllByText("Festival A / Bar / Front").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Festival B / Bar").length).toBeGreaterThan(0);
    expect(screen.queryByText("Taken (#3)")).toBeNull();
    fireEvent.change(input, { target: { value: "Front" } });
    await waitFor(() => expect(screen.getByRole("option").textContent).toContain("POS (#1)"));
    fireEvent.click(screen.getByRole("option"));
    fireEvent.click(screen.getAllByRole("button", { name: "mdm.map" }).at(-1)!);
    await waitFor(() =>
      expect(mockedUpsert).toHaveBeenCalledWith(
        expect.objectContaining({
          nodeId: 0,
          payload: expect.objectContaining({ terminal_id: 1, headwind_device_id: "device-1" }),
        })
      )
    );
  });
});
