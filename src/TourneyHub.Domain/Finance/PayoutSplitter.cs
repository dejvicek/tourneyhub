namespace TourneyHub.Domain.Finance;

/// <summary>
/// Pure, deterministic money-splitting rules. Verified against
/// <c>spec/test-vectors/payout-split.json</c> (see TourneyHub.Domain.Tests).
/// </summary>
public static class PayoutSplitter
{
    /// <summary>
    /// Splits a team payout equally among <paramref name="teamSize"/> members in integer
    /// minor units; the remainder goes entirely to the captain (index 0). FR-075a, BR-008.
    /// Guarantee: the returned shares sum exactly to <paramref name="amountMinor"/>.
    /// </summary>
    public static long[] SplitTeamPayout(long amountMinor, int teamSize)
    {
        if (teamSize < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(teamSize), "Team size must be >= 1.");
        }

        if (amountMinor < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(amountMinor), "Payout must be >= 0.");
        }

        var shares = new long[teamSize];
        var baseShare = amountMinor / teamSize;
        var remainder = amountMinor - (baseShare * teamSize);

        for (var i = 0; i < teamSize; i++)
        {
            shares[i] = baseShare;
        }

        shares[0] += remainder; // remainder to captain (FR-075a)
        return shares;
    }
}
