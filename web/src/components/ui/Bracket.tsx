import { useRef } from 'react'
import { useTranslation } from 'react-i18next'

type MatchData = {
  id: string
  round: number
  slot: number
  participantA?: { id: string; name: string } | null
  participantB?: { id: string; name: string } | null
  state: 'Pending' | 'Ready' | 'InProgress' | 'AwaitingConfirmation' | 'Walkover' | 'Completed'
  winnerId?: string | null
}

type BracketProps = {
  rounds: { round: number; label: string }[]
  matches: MatchData[]
  onMatchClick?: (matchId: string) => void
  highlightParticipantId?: string
}

function ConnectorLine({ animate }: { animate: boolean }) {
  return (
    <div className="flex items-center justify-center w-8 shrink-0">
      <div
        className={`w-0.5 h-4 bg-primary/30 ${
          animate ? 'animate-pulse-gold' : ''
        }`}
      />
    </div>
  )
}

function BracketRound({
  round,
  matches,
  roundIdx,
  onMatchClick,
  highlightParticipantId,
  t,
}: {
  round: { round: number; label: string }
  matches: MatchData[]
  roundIdx: number
  onMatchClick?: (matchId: string) => void
  highlightParticipantId?: string
  t: (key: string) => string
}) {
  return (
    <div className="flex flex-col shrink-0 w-44 min-w-[180px]">
      <div className="text-xs font-heading text-fg-muted uppercase tracking-wider mb-2 px-2">
        {round.label}
      </div>
      <div className="flex flex-col gap-4">
        {roundIdx > 0 && (
          <div className="flex-1" />
        )}
        {matches.map((match) => {
          const isHighlighted =
            highlightParticipantId != null &&
            (match.participantA?.id === highlightParticipantId ||
              match.participantB?.id === highlightParticipantId)

          return (
            <div key={match.id} className="flex items-center">
              <button
                className={`w-full text-left border rounded-md p-2 transition-all text-xs ${
                  match.state === 'Completed'
                    ? 'border-primary/40 bg-primary/5'
                    : 'border-border hover:border-border-hover bg-bg-surface'
                } ${
                  isHighlighted
                    ? 'ring-2 ring-primary shadow-glow'
                    : ''
                } ${onMatchClick ? 'cursor-pointer' : 'cursor-default'}`}
                onClick={() => onMatchClick?.(match.id)}
                disabled={!onMatchClick}
              >
                <div className="flex flex-col gap-1">
                  <div
                    className={`flex items-center justify-between ${
                      match.winnerId === match.participantA?.id
                        ? 'text-primary font-semibold'
                        : 'text-fg-muted'
                    }`}
                  >
                    <span className="truncate">
                      {match.participantA?.name || t('tournament.TBD')}
                    </span>
                    {match.winnerId === match.participantA?.id && (
                      <span className="text-primary text-[10px] ml-1 shrink-0">{t('tournament.W')}</span>
                    )}
                  </div>
                  <div
                    className={`flex items-center justify-between ${
                      match.winnerId === match.participantB?.id
                        ? 'text-primary font-semibold'
                        : 'text-fg-muted'
                    }`}
                  >
                    <span className="truncate">
                      {match.participantB?.name || t('tournament.TBD')}
                    </span>
                    {match.winnerId === match.participantB?.id && (
                      <span className="text-primary text-[10px] ml-1 shrink-0">{t('tournament.W')}</span>
                    )}
                  </div>
                </div>
                {match.state === 'Completed' && (
                  <div className="mt-1 text-[10px] text-fg-muted">{t('tournament.completed')}</div>
                )}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function Bracket({
  rounds,
  matches,
  onMatchClick,
  highlightParticipantId,
}: BracketProps) {
  const { t } = useTranslation()
  const scrollRef = useRef<HTMLDivElement>(null)

  const grouped = rounds.map((r) => ({
    ...r,
    matches: matches.filter((m) => m.round === r.round).sort((a, b) => a.slot - b.slot),
  }))

  if (rounds.length === 0 || matches.length === 0) {
    return (
      <div className="flex items-center justify-center p-12 border border-border rounded-lg bg-bg-surface">
        <p className="text-fg-muted text-sm">{t('tournament.noMatches')}</p>
      </div>
    )
  }

  return (
    <div
      ref={scrollRef}
      className="overflow-x-auto -mx-2 px-2"
    >
      <div className="flex items-start gap-0 min-w-fit">
        {grouped.map((round, roundIdx) => (
          <div key={round.round} className="flex items-start">
            <BracketRound
              round={round}
              matches={round.matches}
              roundIdx={roundIdx}
              onMatchClick={onMatchClick}
              highlightParticipantId={highlightParticipantId}
              t={t}
            />
            {roundIdx < grouped.length - 1 && (
              <div className="flex flex-col justify-center gap-4 mt-10 shrink-0">
                <ConnectorLine animate={false} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
