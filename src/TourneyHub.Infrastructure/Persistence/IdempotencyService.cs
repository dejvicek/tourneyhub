using System.Security.Cryptography;
using System.Text;
using Microsoft.EntityFrameworkCore;

namespace TourneyHub.Infrastructure.Persistence;

internal sealed class IdempotencyService
{
    private readonly TourneyHubDbContext _db;

    public IdempotencyService(TourneyHubDbContext db)
    {
        _db = db;
    }

    public async Task<IdempotencyResult> CheckAndStoreAsync(
        Guid organizationId,
        string key,
        string requestHash,
        CancellationToken ct)
    {
        var existing = await _db.Set<IdempotencyEntry>()
            .FirstOrDefaultAsync(e => e.OrganizationId == organizationId && e.Key == key, ct);

        if (existing is not null)
        {
            if (existing.RequestHash == requestHash)
            {
                return IdempotencyResult.Replay(existing.ResponseBody, existing.ResponseContentType, existing.ResponseStatusCode);
            }

            return IdempotencyResult.Conflict();
        }

        return IdempotencyResult.New(requestHash);
    }

    public async Task StoreResponseAsync(
        Guid organizationId,
        string key,
        string requestHash,
        int statusCode,
        string contentType,
        byte[] body,
        CancellationToken ct)
    {
        var entry = new IdempotencyEntry(
            organizationId,
            key,
            requestHash,
            body,
            contentType,
            statusCode);

        _db.Set<IdempotencyEntry>().Add(entry);
        await _db.SaveChangesAsync(ct);
    }

    public static string ComputeRequestHash(string method, string path, string? body)
    {
        using var sha256 = SHA256.Create();

        var pathBytes = Encoding.UTF8.GetBytes(path);
        var methodBytes = Encoding.UTF8.GetBytes(method);

        sha256.TransformBlock(pathBytes, 0, pathBytes.Length, null, 0);
        sha256.TransformBlock(methodBytes, 0, methodBytes.Length, null, 0);

        if (!string.IsNullOrEmpty(body))
        {
            var bodyBytes = Encoding.UTF8.GetBytes(body);
            sha256.TransformBlock(bodyBytes, 0, bodyBytes.Length, null, 0);
        }

        sha256.TransformFinalBlock(Array.Empty<byte>(), 0, 0);
        return Convert.ToBase64String(sha256.Hash!);
    }
}

internal readonly struct IdempotencyResult
{
    public bool IsReplay { get; }
    public bool IsConflict { get; }
    public byte[] ResponseBody { get; }
    public string ResponseContentType { get; }
    public int ResponseStatusCode { get; }
    public string? RequestHash { get; }

    private IdempotencyResult(bool isReplay, bool isConflict, byte[] responseBody, string responseContentType, int statusCode, string? requestHash)
    {
        IsReplay = isReplay;
        IsConflict = isConflict;
        ResponseBody = responseBody;
        ResponseContentType = responseContentType;
        ResponseStatusCode = statusCode;
        RequestHash = requestHash;
    }

    public static IdempotencyResult New(string requestHash) =>
        new(false, false, Array.Empty<byte>(), string.Empty, 0, requestHash);

    public static IdempotencyResult Replay(byte[] body, string contentType, int statusCode) =>
        new(true, false, body, contentType, statusCode, null);

    public static IdempotencyResult Conflict() =>
        new(false, true, Array.Empty<byte>(), string.Empty, 0, null);
}