import { NewTill } from "@/api";
import { TillProfileSelect, TillTseSelect } from "@/components/features";
import { FormTextField } from "@stustapay/form-components";
import { FormikProps } from "formik";
import { useTranslation } from "react-i18next";

export type TillFormProps<T extends NewTill> = FormikProps<T>;

export function TillForm<T extends NewTill>(props: TillFormProps<T>) {
  const { touched, values, setFieldValue, errors } = props;
  const { t } = useTranslation();
  return (
    <>
      <FormTextField autoFocus name="name" label={t("till.name")} formik={props} />
      <FormTextField name="description" label={t("till.description")} formik={props} />
      <TillProfileSelect
        name="layout"
        label={t("till.profile")}
        error={touched.active_profile_id && !!errors.active_profile_id}
        helperText={(touched.active_profile_id && errors.active_profile_id) as string}
        onChange={(value) => setFieldValue("active_profile_id", value)}
        value={values.active_profile_id}
      />
      <TillTseSelect
        name="layout"
        label={t("till.tse")}
        error={touched.active_tse_id && !!errors.active_tse_id}
        helperText={(touched.active_tse_id && errors.active_tse_id) as string}
        onChange={(value) => setFieldValue("active_tse_id", value)}
        value={values.active_tse_id || null}
      />
    </>
  );
}
