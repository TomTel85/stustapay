import { selectProductAll, useListProductsQuery } from "@/api";
import { useCurrencyFormatter, useCurrentNode } from "@/hooks";
import { Alert, Box, Divider, Stack, Typography } from "@mui/material";
import { Select } from "@stustapay/components";
import { FormCheckbox } from "@stustapay/form-components";
import { NewProductSchema } from "@stustapay/models";
import { FormikProps } from "formik";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { ProductForm } from "./ProductForm";

export const ProductCreateSchema = NewProductSchema.extend({
  create_button: z.boolean(),
  deposit_product_id: z.number().int().nullable(),
});
export type ProductCreateValues = z.infer<typeof ProductCreateSchema>;

export function ProductCreateForm(props: FormikProps<ProductCreateValues>) {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const formatCurrency = useCurrencyFormatter();
  const { data, isLoading, isError } = useListProductsQuery(
    { nodeId: currentNode.id },
    { skip: !props.values.create_button }
  );
  const depositProducts = data ? selectProductAll(data).filter((product) => product.is_returnable) : [];

  return (
    <>
      {props.status?.buttonCreationFailed && <Alert severity="warning">{t("product.buttonCreationFailed")}</Alert>}
      {props.status?.productCreationFailed && <Alert severity="error">{t("product.productCreationFailed")}</Alert>}
      <Box
        component="fieldset"
        disabled={props.isSubmitting || props.status?.productCreated}
        sx={{ border: 0, p: 0, m: 0, minWidth: 0 }}
      >
        <Stack spacing={2}>
          <ProductForm {...props} />
        </Stack>
      </Box>
      <Divider />
      <Typography component="h2" variant="h6">
        {t("product.buttonSection")}
      </Typography>
      <FormCheckbox
        name="create_button"
        label={t("product.createButton")}
        formik={props}
        disabled={props.isSubmitting}
      />
      {props.values.create_button && (
        <>
          <Typography variant="body2" color="text.secondary">
            {t("product.createButtonHelp")}
          </Typography>
          <Select
            label={t("product.depositProduct")}
            multiple={false}
            options={depositProducts}
            value={depositProducts.find((product) => product.id === props.values.deposit_product_id) ?? null}
            onChange={(product) => props.setFieldValue("deposit_product_id", product?.id ?? null)}
            formatOption={(product) => `${product.name} (${formatCurrency(product.price)})`}
            renderOption={({ key, ...optionProps }, product) => (
              <li key={key} {...optionProps}>{`${product.name} (${formatCurrency(product.price)})`}</li>
            )}
            disabled={props.isSubmitting || isLoading || isError}
            error={isError}
          />
          <Typography variant="body2" color={isError ? "error" : "text.secondary"}>
            {t(isError ? "product.depositLoadFailed" : "product.depositProductHelp")}
          </Typography>
        </>
      )}
    </>
  );
}
