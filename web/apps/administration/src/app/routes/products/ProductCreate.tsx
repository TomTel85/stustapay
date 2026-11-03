import { Product, useCreateProductMutation, useCreateTillButtonMutation } from "@/api";
import { ProductRoutes } from "@/app/routes";
import { CreateLayout } from "@/components";
import { useCurrentNode } from "@/hooks";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { ProductCreateForm, ProductCreateSchema, ProductCreateValues } from "./ProductCreateForm";
import { withPrivilegeGuard } from "@/app/layout";

const initialValues: ProductCreateValues = {
  create_button: true,
  deposit_product_id: null,
  name: "",
  price: 0,
  tax_rate_id: null as unknown as number,
  fixed_price: true,
  price_in_vouchers: 0,
  restrictions: [],
  is_returnable: false,
  is_donation: false,
};

const ProductCreateAtNode: React.FC<{ nodeId: number }> = ({ nodeId }) => {
  const { t } = useTranslation();
  const [createProduct] = useCreateProductMutation();
  const [createTillButton] = useCreateTillButtonMutation();
  const savedProduct = React.useRef<Product | null>(null);

  return (
    <CreateLayout
      title={t("product.create")}
      submitLabel={t("add")}
      successRoute={ProductRoutes.list()}
      initialValues={initialValues}
      validationSchema={ProductCreateSchema}
      onSubmit={async ({ create_button, deposit_product_id, ...product }, { setStatus }) => {
        try {
          if (!savedProduct.current) {
            savedProduct.current = await createProduct({ nodeId, newProduct: product }).unwrap();
          }
          setStatus({ productCreated: true });
          if (create_button) {
            await createTillButton({
              nodeId,
              newTillButton: {
                name: savedProduct.current.name,
                product_ids: [savedProduct.current.id, ...(deposit_product_id == null ? [] : [deposit_product_id])],
              },
            }).unwrap();
          }
        } catch (error) {
          setStatus(
            savedProduct.current
              ? { productCreated: true, buttonCreationFailed: true }
              : { productCreationFailed: true }
          );
          throw error;
        }
      }}
      form={ProductCreateForm}
    />
  );
};

export const ProductCreate: React.FC = withPrivilegeGuard("node_administration", () => {
  const { currentNode } = useCurrentNode();
  return <ProductCreateAtNode key={currentNode.id} nodeId={currentNode.id} />;
});
