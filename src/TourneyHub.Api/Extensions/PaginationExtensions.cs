using System.Text.Json;

namespace TourneyHub.Api.Extensions;

internal static class PaginationExtensions
{
    public static IResult OkPaginated<T>(
        this IResultExtensions _,
        IReadOnlyCollection<T> items,
        int limit,
        Func<T, string> cursorSelector,
        bool hasMore)
    {
        if (items.Count == 0)
        {
            return Results.Ok(new PaginatedResult<T>(items, null));
        }

        if (!hasMore)
        {
            return Results.Ok(new PaginatedResult<T>(items, null));
        }

        var lastItem = items.Last();
        var nextCursor = cursorSelector(lastItem);

        return Results.Ok(new PaginatedResult<T>(items, nextCursor));
    }

    public sealed record PaginatedResult<T>(
        IReadOnlyCollection<T> Items,
        string? NextCursor);
}