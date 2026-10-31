import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { get, type Page } from "./api";
import { setCurrencySymbol } from "./money";
import type { Customer, Meta, PaymentTerm, Plan, Product, QuotationTemplate, Tax, User } from "./types";
import { useToast } from "../components/ui";

export function useMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: async () => {
      const meta = await get<Meta>("meta/");
      setCurrencySymbol(meta.company.currency_symbol);
      return meta;
    },
    staleTime: Infinity,
  });
}

export function useChoices(name: string) {
  return useMeta().data?.choices[name] ?? [];
}

// Small reference lists used by forms and filters.
export const useTaxes = () => useQuery({ queryKey: ["taxes"], queryFn: () => get<Tax[]>("taxes/") });
export const usePaymentTerms = () => useQuery({ queryKey: ["payment-terms"], queryFn: () => get<PaymentTerm[]>("payment-terms/") });
export const usePlans = () => useQuery({ queryKey: ["plans", "all"], queryFn: () => get<Page<Plan>>("plans/", { page_size: 200 }) });
export const useProducts = () => useQuery({ queryKey: ["products", "all"], queryFn: () => get<Page<Product>>("products/", { page_size: 200 }) });
export const useTemplates = () => useQuery({ queryKey: ["quotation-templates"], queryFn: () => get<QuotationTemplate[]>("quotation-templates/") });
export const useTeam = () => useQuery({ queryKey: ["team"], queryFn: () => get<Page<User>>("team/", { page_size: 200 }) });
export const useCustomerSearch = (search: string) =>
  useQuery({ queryKey: ["customers", "pick", search], queryFn: () => get<Page<Customer>>("customers/", { search, page_size: 20 }) });

/** A mutation that toasts and refreshes queries; errors are toasted too. */
export function useAction<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  opts: { success?: string | ((r: TResult) => string); invalidate?: unknown[][]; onSuccess?: (r: TResult) => void } = {},
) {
  const toast = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (result) => {
      if (opts.success) toast(typeof opts.success === "function" ? opts.success(result) : opts.success);
      (opts.invalidate ?? []).forEach((key) => queryClient.invalidateQueries({ queryKey: key }));
      opts.onSuccess?.(result);
    },
    onError: (error: Error) => toast(error.message, "error"),
  });
}

/** List state (page, filters) kept in the URL so views are shareable. */
export function useListParams(defaults: Record<string, string> = {}) {
  const [params, setParams] = useSearchParams();
  const value = (key: string) => params.get(key) ?? defaults[key] ?? "";
  const set = (changes: Record<string, string | number | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "" || v === defaults[k]) next.delete(k);
      else next.set(k, String(v));
    }
    if (!("page" in changes)) next.delete("page");
    setParams(next, { replace: true });
  };
  return { value, set, page: Number(params.get("page") ?? 1) };
}
