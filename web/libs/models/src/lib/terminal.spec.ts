import { NewTerminalSchema, UpdateTerminalSchema } from "./terminal";

describe("terminal identity defaults", () => {
  it("defaults new terminals to device identity", () => {
    expect(NewTerminalSchema.parse({ name: "New terminal" }).login_mode).toBe("device");
  });

  it("allows explicitly creating a personal terminal", () => {
    expect(NewTerminalSchema.parse({ name: "Personal", login_mode: "personal" }).login_mode).toBe("personal");
  });

  it("does not select a new mode when editing an existing terminal", () => {
    expect(UpdateTerminalSchema.parse({ id: 1, name: "Existing" }).login_mode).toBeUndefined();
    expect(UpdateTerminalSchema.parse({ id: 1, name: "Existing", login_mode: "personal" }).login_mode).toBe("personal");
  });
});
