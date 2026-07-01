namespace TourneyHub.Domain.Common;

/// <summary>
/// Money as integer MINOR units (e.g. cents) + ISO-4217 currency.
/// Never floating point (BR-008, FR-081). Compute may use decimal, but persistence
/// and transport are always integer minor units + currency.
/// </summary>
public readonly record struct Money(long AmountMinor, string Currency)
{
    /// <summary>Validating factory: currency must be a 3-letter ISO-4217 code.</summary>
    public static Money Of(long amountMinor, string currency)
    {
        if (string.IsNullOrWhiteSpace(currency) || currency.Length != 3)
        {
            throw new ArgumentException("Currency must be a 3-letter ISO-4217 code.", nameof(currency));
        }

        return new Money(amountMinor, currency);
    }

    public static Money Zero(string currency) => Of(0, currency);
}
