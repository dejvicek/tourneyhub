using System.Security.Cryptography;
using System.Text;

namespace TourneyHub.Domain.Logic.Formats;

public sealed class SingleEliminationBracket
{
    public int TotalRounds { get; init; }
    public int BracketSize { get; init; }
    public int ByeCount { get; init; }
    public List<BracketMatch> Matches { get; init; } = [];
}

public sealed class BracketMatch
{
    public int RoundNumber { get; set; }
    public int PositionInRound { get; init; }
    public int? SeedA { get; set; }
    public int? SeedB { get; set; }
    public bool IsByeMatch { get; set; }
    public int? AdvanceToRound { get; init; }
    public int? AdvanceToPosition { get; init; }
    public int? AdvancingSeed { get; set; }
}

public static class SingleEliminationGenerator
{
    public static SingleEliminationBracket Generate(int participantCount, string rngSeed)
    {
        if (participantCount < 2)
            throw new BracketGeneratorException("insufficient_participants", "At least 2 participants are required for a single-elimination bracket.");

        int bracketSize = NextPowerOfTwo(participantCount);
        int numRounds = (int)Math.Log2(bracketSize);
        int byeCount = bracketSize - participantCount;

        List<int> slotOrder = BuildSlotOrder(bracketSize);

        var allMatches = new List<BracketMatch>();
        var roundMatches = new Dictionary<int, List<BracketMatch>>();

        for (int round = 1; round <= numRounds; round++)
        {
            int matchesInRound = bracketSize / (int)Math.Pow(2, round);
            var currentRound = new List<BracketMatch>();

            for (int pos = 1; pos <= matchesInRound; pos++)
            {
                int nextRound = round < numRounds ? round + 1 : 0;
                int nextPos = round < numRounds ? (pos + 1) / 2 : 0;

                if (round == 1)
                {
                    int seedA = slotOrder[(pos - 1) * 2];
                    int seedB = slotOrder[(pos - 1) * 2 + 1];

                    bool aIsBye = seedA > participantCount;
                    bool bIsBye = seedB > participantCount;

                    if (aIsBye && bIsBye)
                        throw new BracketGeneratorException("double_bye", "Internal error: bye on both sides of a match.");

                    var match = new BracketMatch
                    {
                        RoundNumber = round,
                        PositionInRound = pos,
                        SeedA = aIsBye ? null : seedA,
                        SeedB = bIsBye ? null : seedB,
                        IsByeMatch = aIsBye || bIsBye,
                        AdvanceToRound = nextRound == 0 ? null : nextRound,
                        AdvanceToPosition = nextRound == 0 ? null : nextPos,
                    };

                    if (match.IsByeMatch)
                    {
                        match.AdvancingSeed = aIsBye ? seedB : seedA;
                    }

                    currentRound.Add(match);
                }
                else
                {
                    var match = new BracketMatch
                    {
                        RoundNumber = round,
                        PositionInRound = pos,
                        IsByeMatch = false,
                        AdvanceToRound = nextRound == 0 ? null : nextRound,
                        AdvanceToPosition = nextRound == 0 ? null : nextPos,
                    };

                    currentRound.Add(match);
                }
            }

            roundMatches[round] = currentRound;
            allMatches.AddRange(currentRound);
        }

        PropagateByeAdvances(roundMatches, numRounds);

        return new SingleEliminationBracket
        {
            TotalRounds = numRounds,
            BracketSize = bracketSize,
            ByeCount = byeCount,
            Matches = allMatches,
        };
    }

    private static void PropagateByeAdvances(Dictionary<int, List<BracketMatch>> roundMatches, int numRounds)
    {
        for (int round = 1; round < numRounds; round++)
        {
            var currentRound = roundMatches[round];
            var nextRound = roundMatches[round + 1];

            foreach (var match in currentRound)
            {
                if (!match.IsByeMatch || match.AdvancingSeed is null) continue;
                if (match.AdvanceToRound is null || match.AdvanceToPosition is null) continue;

                var targetMatch = nextRound.First(m =>
                    m.PositionInRound == match.AdvanceToPosition.Value);

                int sourcePos = match.PositionInRound;
                if (sourcePos % 2 == 1)
                {
                    targetMatch.SeedA = match.AdvancingSeed;
                }
                else
                {
                    targetMatch.SeedB = match.AdvancingSeed;
                }
            }

            foreach (var match in nextRound)
            {
                if (match.SeedA is not null && match.SeedB is not null)
                {
                    match.IsByeMatch = false;
                }
            }
        }
    }

    public static List<int> ShuffleSeeds(int participantCount, string rngSeed)
    {
        ArgumentNullException.ThrowIfNull(rngSeed);
        var seeds = Enumerable.Range(1, participantCount).ToList();
        if (rngSeed.Length == 0) return seeds;

        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(rngSeed));
        var rng = new Random(BitConverter.ToInt32(hash, 0));

        for (int i = seeds.Count - 1; i > 0; i--)
        {
            int j = rng.Next(i + 1);
            (seeds[i], seeds[j]) = (seeds[j], seeds[i]);
        }

        return seeds;
    }

    internal static int NextPowerOfTwo(int n)
    {
        if (n < 2) return 2;
        n--;
        n |= n >> 1;
        n |= n >> 2;
        n |= n >> 4;
        n |= n >> 8;
        n |= n >> 16;
        return n + 1;
    }

    internal static List<int> BuildSlotOrder(int size)
    {
        var result = new List<int> { 1, 2 };
        while (result.Count < size)
        {
            var expanded = new List<int>();
            foreach (var s in result)
            {
                expanded.Add(s);
                expanded.Add(result.Count * 2 + 1 - s);
            }
            result = expanded;
        }

        return result;
    }

    public static List<int> GetByeSeeds(int participantCount)
    {
        int bracketSize = NextPowerOfTwo(participantCount);
        int byeCount = bracketSize - participantCount;
        return Enumerable.Range(1, byeCount).ToList();
    }

    public static int RealMatchCount(int participantCount)
    {
        return participantCount - 1;
    }
}

public class BracketGeneratorException : Exception
{
    public string Code { get; }
    public BracketGeneratorException(string code, string message) : base(message) { Code = code; }
}