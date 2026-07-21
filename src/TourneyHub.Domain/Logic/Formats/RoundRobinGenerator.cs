using System.Security.Cryptography;
using System.Text;

namespace TourneyHub.Domain.Logic.Formats;

public sealed class RoundRobinRound
{
    public int RoundNumber { get; init; }
    public List<RoundRobinPairing> Pairings { get; init; } = [];
    public List<int> Byes { get; init; } = [];
}

public sealed class RoundRobinPairing
{
    public int SeedA { get; init; }
    public int SeedB { get; init; }
}

public sealed class RoundRobinSchedule
{
    public int ParticipantCount { get; init; }
    public int TotalRounds { get; init; }
    public int TotalMatches { get; init; }
    public List<RoundRobinRound> Rounds { get; init; } = [];
}

public static class RoundRobinGenerator
{
    public static RoundRobinSchedule Generate(int participantCount)
    {
        if (participantCount < 2)
            throw new RoundRobinGeneratorException("insufficient_participants", "At least 2 participants are required for a round-robin tournament.");

        bool isOdd = participantCount % 2 == 1;
        int totalParticipants = isOdd ? participantCount + 1 : participantCount;
        int totalRounds = totalParticipants - 1;
        int totalMatches = participantCount * (participantCount - 1) / 2;

        var participants = new int[totalParticipants];
        if (isOdd)
        {
            participants[0] = 0;
            for (int i = 1; i < totalParticipants; i++)
                participants[i] = i;
        }
        else
        {
            for (int i = 0; i < totalParticipants; i++)
                participants[i] = i + 1;
        }

        var rounds = new List<RoundRobinRound>();

        for (int round = 0; round < totalRounds; round++)
        {
            var roundObj = new RoundRobinRound
            {
                RoundNumber = round + 1,
            };

            for (int j = 0; j < totalParticipants / 2; j++)
            {
                int a = participants[j];
                int b = participants[totalParticipants - 1 - j];

                if (isOdd && (a == 0 || b == 0))
                {
                    int bye = a == 0 ? b : a;
                    roundObj.Byes.Add(bye);
                }
                else
                {
                    roundObj.Pairings.Add(new RoundRobinPairing
                    {
                        SeedA = a,
                        SeedB = b,
                    });
                }
            }

            rounds.Add(roundObj);

            int last = participants[totalParticipants - 1];
            for (int k = totalParticipants - 1; k > 1; k--)
                participants[k] = participants[k - 1];
            participants[1] = last;
        }

        return new RoundRobinSchedule
        {
            ParticipantCount = participantCount,
            TotalRounds = totalRounds,
            TotalMatches = totalMatches,
            Rounds = rounds,
        };
    }

    public static List<int> ShuffleParticipants(int participantCount, string rngSeed)
    {
        ArgumentNullException.ThrowIfNull(rngSeed);
        var participants = Enumerable.Range(1, participantCount).ToList();
        if (rngSeed.Length == 0) return participants;

        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(rngSeed));
        var rng = new Random(BitConverter.ToInt32(hash, 0));

        for (int i = participants.Count - 1; i > 0; i--)
        {
            int j = rng.Next(i + 1);
            (participants[i], participants[j]) = (participants[j], participants[i]);
        }

        return participants;
    }
}

public class RoundRobinGeneratorException : Exception
{
    public string Code { get; }
    public RoundRobinGeneratorException(string code, string message) : base(message) { Code = code; }
}
