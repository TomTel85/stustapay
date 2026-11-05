import { hasAnyPrivilege } from "@/core/privileges";
import { OrderRoutes, UserToRoleRoutes } from "./routes";

test("uses the backend's user management privilege for role assignments", () => {
  expect(UserToRoleRoutes.privilege).toBe("user_management");
});

describe("OrderRoutes", () => {
  test("accepts can_book_orders for order access", () => {
    expect(hasAnyPrivilege(["can_book_orders"], OrderRoutes.privilege)).toBe(true);
  });

  test("accepts node_administration for order access", () => {
    expect(hasAnyPrivilege(["node_administration"], OrderRoutes.privilege)).toBe(true);
  });
});
