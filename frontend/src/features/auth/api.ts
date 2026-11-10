import { queryOptions } from "@tanstack/react-query";

import { dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";

export const authQueries = {
  // Provisional: GET /api/v1/me is not in openapi.json yet.
  me: () =>
    queryOptions({
      queryKey: ["me"],
      queryFn: ({ signal }) =>
        dataOf(provisionalApi.GET("/api/v1/me", { signal })),
    }),
};
