import { useCheckCheckoutMutation, useCreateCheckoutMutation, useGetCustomerQuery } from "@/api";
import { usePublicConfig } from "@/hooks";
import i18n from "@/i18n";
import { Cancel as CancelIcon, CheckCircle as CheckCircleIcon } from "@mui/icons-material";
import { Alert, AlertTitle, Box, Button, Grid, LinearProgress, Link, Stack } from "@mui/material";
import { Loading } from "@stustapay/components";
import { FormCurrencyInput } from "@stustapay/form-components";
import { toFormikValidationSchema } from "@stustapay/utils";
import { Form, Formik, FormikHelpers } from "formik";
import * as React from "react";
import { Trans, useTranslation } from "react-i18next";
import { Navigate, Link as RouterLink } from "react-router-dom";
import { toast } from "react-toastify";
import { z } from "zod";
import type { SumUpCard, SumUpCardInstance, SumUpResponseType } from "./SumUpCard";

const TopUpSchema = z.object({
  amount: z.number().int(i18n.t("topup.errorAmountMustBeIntegral")).positive(i18n.t("topup.errorAmountGreaterZero")),
});

type FormVal = z.infer<typeof TopUpSchema>;

const initialValues: FormVal = { amount: 0 };

declare global {
  const SumUpCard: SumUpCard;
}

type TopUpState =
  | { stage: "initial" }
  | { stage: "sumup"; topupAmount: number; checkoutId: string; orderUUID: string }
  | { stage: "success" }
  | { stage: "error"; message?: string }
  | { stage: "cancelled"; message?: string };

const initialState: TopUpState = { stage: "initial" };

type TopUpStateAction =
  | { type: "created-checkout"; topupAmount: number; checkoutId: string; orderUUID: string }
  | { type: "sumup-success" }
  | { type: "sumup-error"; message?: string }
  | { type: "sumup-cancelled"; message?: string }
  | { type: "reset" };

const reducer = (state: TopUpState, action: TopUpStateAction): TopUpState => {
  switch (action.type) {
    case "created-checkout":
      if (state.stage !== "initial") {
        return state;
      }
      return {
        stage: "sumup",
        topupAmount: action.topupAmount,
        checkoutId: action.checkoutId,
        orderUUID: action.orderUUID,
      };
    case "sumup-success":
      if (state.stage !== "sumup") {
        return state;
      }
      return { stage: "success" };
    case "sumup-error":
      if (state.stage !== "sumup") {
        return state;
      }
      return { stage: "error", message: action.message };
    case "sumup-cancelled":
      if (state.stage !== "sumup") {
        return state;
      }
      return { stage: "cancelled", message: action.message };
    case "reset":
      return initialState;
  }
};

const Container: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <Grid container justifyItems="center" justifyContent="center" sx={{ paddingX: 0.5 }}>
      <Grid item xs={12} sm={8} sx={{ mt: 2 }}>
        {children}
      </Grid>
    </Grid>
  );
};

type SumUpCardRespHandler = (type: SumUpResponseType, body: object) => void;
type SumUpCardLoadHandler = () => void;

export const TopUp: React.FC = () => {
  const { t, i18n } = useTranslation();

  const config = usePublicConfig();

  const { data: customer, error: customerError, isLoading: isCustomerLoading } = useGetCustomerQuery();
  const [createCheckout] = useCreateCheckoutMutation();
  const [checkCheckout] = useCheckCheckoutMutation();

  const sumupCard = React.useRef<SumUpCardInstance | undefined>(undefined);
  const handleSumupCardResp = React.useRef<SumUpCardRespHandler | undefined>(undefined);
  const handleSumupCardLoad = React.useRef<SumUpCardLoadHandler | undefined>(undefined);

  const [state, dispatch] = React.useReducer(reducer, initialState);

  const reset = () => {
    dispatch({ type: "reset" });
  };

  React.useEffect(() => {
    handleSumupCardResp.current = (type: SumUpResponseType, body: object) => {
      if (state.stage !== "sumup") {
        return;
      }
      if (type === "invalid" && "message" in body && typeof body.message === "string") {
        toast.error(body.message);
      }

      if (type === "error" || type === "success") {
        // If SumUp reports success, we should trust it and retry a few times if our backend has issues
        const maxRetries = type === "success" ? 3 : 1;
        let retryCount = 0;
        
        const checkPaymentStatus = () => {
          checkCheckout({ checkCheckoutPayload: { order_uuid: state.orderUUID } })
            .unwrap()
            .then((resp) => {
              if (sumupCard.current) {
                sumupCard.current.unmount();
                sumupCard.current = undefined;
              }

              if (resp.status === "FAILED") {
                dispatch({ type: "sumup-cancelled", message: t("topup.cancelled.message") });
              } else if (resp.status === "PAID") {
                dispatch({ type: "sumup-success" });
              } else if (resp.status === "PENDING" && type === "success" && retryCount < maxRetries) {
                // If SumUp reports success but our backend still shows pending, retry after a delay
                retryCount++;
                const delay = 1000 * retryCount; // Increasing delay: 1s, 2s, 3s
                console.log(`Payment reported as success by SumUp but still pending in backend, retrying in ${delay/1000}s (attempt ${retryCount}/${maxRetries})`);
                setTimeout(checkPaymentStatus, delay);
              } else {
                // Payment still pending after retries
                if (type === "success") {
                  // SumUp confirmed success, so we'll show success even if our backend is delayed
                  console.log("SumUp confirms payment success, but backend still shows pending. Showing success to user.");
                  dispatch({ type: "sumup-success" });
                }
              }
            })
            .catch((error) => {
              // If we get a 404 error or any 4xx error, but SumUp reported success,
              // the payment might have succeeded but there was a database error in our backend
              if (type === "success") {
                if (retryCount < maxRetries) {
                  // Retry after a delay
                  retryCount++;
                  const delay = 1000 * retryCount; // Increasing delay: 1s, 2s, 3s
                  console.log(`SumUp reports success but API check failed, retrying in ${delay/1000}s (attempt ${retryCount}/${maxRetries})`, error);
                  setTimeout(checkPaymentStatus, delay);
                } else {
                  // After retries, if SumUp confirmed success, show success to user
                  console.log("SumUp reports success, but checkout check failed with error after retries:", error);
                  dispatch({ type: "sumup-success" });
                }
              } else if (error?.status === 404 || (error?.data && error?.data.detail === "Order not found")) {
                // The order might have been cancelled in the background
                dispatch({ type: "sumup-cancelled", message: t("topup.cancelled.message") });
              } else {
                console.error("Error checking payment status:", error);
                toast.error(t("topup.unexpectedError"));
                dispatch({ type: "sumup-error" });
              }
            });
        };
        
        checkPaymentStatus();
      }
    };

    handleSumupCardLoad.current = () => {
      console.log("sumup card loaded");
    };
  }, [checkCheckout, dispatch, state]);

  React.useEffect(() => {
    if (state.stage !== "sumup") {
      return;
    }
    const config = {
      id: "sumup-card",
      checkoutId: state.checkoutId,
      onLoad: handleSumupCardLoad.current,
      onResponse: handleSumupCardResp.current,
      locale: i18n.language,
    };
    if (sumupCard.current) {
      sumupCard.current.update(config);
    } else {
      try {
        sumupCard.current = SumUpCard.mount(config);
        // sumupCard.current = SumUpCardMock.mount(config);
      } catch (e) {
        console.error("Mounting sumup card threw an error", e);
      }
    }
  }, [config, state, i18n, checkCheckout, dispatch]);

  // Add an effect to check for stalled payments
  React.useEffect(() => {
    if (state.stage !== "sumup") {
      return;
    }

    // Set up a timeout to check if the payment is taking too long (2 minutes)
    const timeoutId = setTimeout(() => {
      checkCheckout({ checkCheckoutPayload: { order_uuid: state.orderUUID } })
        .unwrap()
        .then((resp) => {
          if (resp.status === "PENDING") {
            // Still pending after 2 minutes, offer to restart
            toast.warning(t("topup.paymentTakingTooLong"));
          }
        })
        .catch(() => {
          // Ignore errors here
        });
    }, 2 * 60 * 1000);  // 2 minutes

    return () => {
      clearTimeout(timeoutId);
    };
  }, [state, checkCheckout, t]);

  if (!config.sumup_topup_enabled) {
    toast.error(t("topup.sumupTopupDisabled"));
    return <Navigate to="/" />;
  }

  if (isCustomerLoading || (!customer && !customerError)) {
    return <Loading />;
  }

  if (customerError || !customer) {
    toast.error("Error loading customer");
    return <Navigate to="/" />;
  }

  const onSubmit = (values: FormVal, { setSubmitting }: FormikHelpers<FormVal>) => {
    setSubmitting(true);
    createCheckout({ createCheckoutPayload: values })
      .unwrap()
      .then((checkout) => {
        dispatch({
          type: "created-checkout",
          checkoutId: checkout.checkout_id,
          topupAmount: values.amount,
          orderUUID: checkout.order_uuid,
        });
        setSubmitting(false);
      })
      .catch((error) => {
        console.error(error);
        setSubmitting(false);
      });
  };

  switch (state.stage) {
    case "initial":
      return (
        <Container>
          <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
            {t("topup.description")}
          </Alert>
          <Formik
            initialValues={initialValues}
            validationSchema={toFormikValidationSchema(TopUpSchema)}
            onSubmit={onSubmit}
          >
            {(formik) => (
              <Form onSubmit={formik.handleSubmit}>
                <Stack spacing={2}>
                  <FormCurrencyInput name="amount" label={t("topup.amount")} variant="outlined" formik={formik} />
                  {formik.isSubmitting && <LinearProgress />}
                  <Button type="submit" variant="contained" color="primary" disabled={formik.isSubmitting}>
                    {t("topup.next")}
                  </Button>
                </Stack>
              </Form>
            )}
          </Formik>
        </Container>
      );
    case "sumup":
      return (
        <Container>
          <div id="sumup-card"></div>
        </Container>
      );
    case "success":
      return (
        <Container>
          <Alert severity="success">
            <AlertTitle>{t("topup.success.title")}</AlertTitle>
            <Trans i18nKey={"topup.success.message"}>
              continue to to the
              <Link component={RouterLink} to="/">
                overview page
              </Link>
            </Trans>
          </Alert>
          <Box
            sx={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              width: "100%",
            }}
          >
            <CheckCircleIcon color="success" sx={{ fontSize: "15em" }} />
          </Box>
        </Container>
      );
    case "error":
      return (
        <Container>
          <Alert severity="error" action={<Button onClick={reset}>{t("topup.tryAgain")}</Button>}>
            <AlertTitle>{t("topup.error.title")}</AlertTitle>
            {t("topup.error.message")}
            {/* <Trans i18nKey={"topup.error.message"}>An error occurred: {{ message: state.message }}, please</Trans> */}
          </Alert>
          <Box
            sx={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              width: "100%",
            }}
          >
            <CancelIcon color="error" sx={{ fontSize: "15em" }} />
          </Box>
        </Container>
      );
    case "cancelled":
      return (
        <Container>
          <Alert severity="warning">
            <AlertTitle>{t("topup.cancelled.title")}</AlertTitle>
            {state.message || t("topup.cancelled.defaultMessage")}
          </Alert>
          <Box
            sx={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              mt: 2,
            }}
          >
            <Button
              startIcon={<CancelIcon />}
              onClick={reset}
              variant="contained"
              color="primary"
              sx={{ mt: 2 }}
            >
              {t("topup.tryAgain")}
            </Button>
          </Box>
        </Container>
      );
  }
};
