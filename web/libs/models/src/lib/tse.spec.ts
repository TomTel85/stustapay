import { NewTseSchema, UpdateTseSchema } from "./tse";

describe("TSE provider schemas", () => {
  it("uses Fiskaly profile names without requiring USB connection fields", () => {
    const tse = NewTseSchema.parse({
      name: "Festival TSE",
      type: "fiskaly",
      fiskaly_profile: "festival-production",
    });

    expect(tse).toMatchObject({
      type: "fiskaly",
      fiskaly_profile: "festival-production",
      serial: null,
      ws_url: "",
      ws_timeout: 5,
      password: "",
    });
  });

  it("keeps USB serial and websocket validation for new TSEs", () => {
    expect(
      NewTseSchema.safeParse({
        name: "USB TSE",
        type: "diebold_nixdorf",
        serial: "",
        ws_url: "",
      }).success
    ).toBe(false);

    expect(
      NewTseSchema.safeParse({
        name: "USB TSE",
        type: "diebold_nixdorf",
        serial: "serial-123",
        ws_url: "ws://tse.local",
      }).success
    ).toBe(true);
  });

  it("validates the Fiskaly profile during edits without requiring USB fields", () => {
    expect(
      UpdateTseSchema.safeParse({
        name: "Festival TSE",
        type: "fiskaly",
        fiskaly_profile: "festival-production",
      }).success
    ).toBe(true);

    expect(
      UpdateTseSchema.safeParse({
        name: "Festival TSE",
        type: "fiskaly",
        fiskaly_profile: "  ",
      }).success
    ).toBe(false);
  });
});
