import { selectCashRegisterById, useListCashRegistersAdminQuery } from "@/api";
import { withPrivilegeGuard } from "@/app/layout";
import { CashRegistersRoutes } from "@/app/routes";
import { useCurrentNode } from "@/hooks";
import { Alert, Button, LinearProgress, Paper, TextField, Typography } from "@mui/material";
import { Loading } from "@stustapay/components";
import { toFormikValidationSchema } from "@stustapay/utils";
import { Form, Formik, FormikHelpers } from "formik";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

// Define schema for the form values
const ModifyBalanceSchema = z.object({
  amount: z.number().min(0.01, { message: "Amount must be greater than 0" }),
});

// Type for form values
type FormValues = z.infer<typeof ModifyBalanceSchema>;

// Create the API endpoint for modifying register balance
import { api } from "@/api/generated/api";

const enhancedApi = api.injectEndpoints({
  endpoints: (build) => ({
    modifyRegisterBalance: build.mutation<any, { nodeId: number; modifyRegisterBalancePayload: { cashier_id: number; amount: number } }>({
      query: ({ nodeId, modifyRegisterBalancePayload }) => ({
        url: `/till-registers/modify-balance`,
        method: "POST",
        body: modifyRegisterBalancePayload,
        params: {
          node_id: nodeId,
        },
      }),
      invalidatesTags: ["till-registers"],
    }),
  }),
});

export const { useModifyRegisterBalanceMutation } = enhancedApi;

export const CashRegisterModifyBalance: React.FC = withPrivilegeGuard("node_administration", () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { currentNode } = useCurrentNode();
  const { registerId } = useParams();
  const { register, isLoading, error } = useListCashRegistersAdminQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ data, ...rest }) => ({
        ...rest,
        register: data ? selectCashRegisterById(data, Number(registerId)) : undefined,
      }),
    }
  );
  const [modifyRegisterBalance] = useModifyRegisterBalanceMutation();

  // Set initial values for the form
  const initialValues: FormValues = React.useMemo(() => {
    return {
      amount: 0,
    };
  }, []);

  if (error) {
    return <Navigate to={CashRegistersRoutes.list()} />;
  }

  if (isLoading || !register) {
    return <Loading />;
  }

  // Show an error if the register doesn't have a cashier assigned
  const hasCashier = register.current_cashier_id != null;

  const handleSubmit = (values: FormValues, { setSubmitting }: FormikHelpers<FormValues>) => {
    if (!hasCashier) {
      return;
    }
    setSubmitting(true);

    modifyRegisterBalance({
      nodeId: currentNode.id,
      modifyRegisterBalancePayload: { 
        cashier_id: register.current_cashier_id!, 
        amount: values.amount
      },
    })
      .unwrap()
      .then(() => {
        setSubmitting(false);
        navigate(CashRegistersRoutes.list());
      })
      .catch((err) => {
        setSubmitting(false);
        console.warn("error in modifying cash register balance", err);
      });
  };

  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        {t("register.modifyBalance")}
      </Typography>
      {!hasCashier ? (
        <Alert severity="error">
          {t("register.cannotModifyNotAssigned")}
        </Alert>
      ) : (
        <Formik
          initialValues={initialValues}
          onSubmit={handleSubmit}
          validationSchema={toFormikValidationSchema(ModifyBalanceSchema)}
        >
          {({ values, handleChange, handleSubmit, isSubmitting, errors, touched }) => (
            <Form onSubmit={handleSubmit}>
              <TextField
                fullWidth
                variant="standard"
                label={t("register.amount")}
                type="number"
                name="amount"
                value={values.amount}
                onChange={handleChange}
                error={touched.amount && !!errors.amount}
                helperText={(touched.amount && errors.amount) as string}
                inputProps={{ min: 0, step: 0.01 }}
                sx={{ mb: 2 }}
              />

              <Typography variant="body2" sx={{ mb: 2 }}>
                {t("register.modifyBalanceDescription")}
              </Typography>

              {isSubmitting && <LinearProgress />}
              <Button
                type="submit"
                fullWidth
                variant="contained"
                color="primary"
                disabled={isSubmitting}
                sx={{ mt: 1 }}
              >
                {t("submit")}
              </Button>
            </Form>
          )}
        </Formik>
      )}
    </Paper>
  );
}); 