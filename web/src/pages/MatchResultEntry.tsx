import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useTournamentOverview } from '../hooks/useTournament'
import { useUpdateMatchResult, useForfeitMatch } from '../hooks/useMatchResult'
import { Button, Card, Modal } from '../components/ui'
import { useToast } from '../hooks/useToast'

export default function MatchResultEntry() {
  const { t } = useTranslation()
  const { id, matchId } = useParams<{ id: string; matchId: string }>()
  const navigate = useNavigate()
  const { data } = useTournamentOverview(id!)
  const updateResult = useUpdateMatchResult(matchId!)
  const forfeit = useForfeitMatch(matchId!)
  const { toast } = useToast()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [forfeitOpen, setForfeitOpen] = useState<false | 'a' | 'b'>(false)
  const [pendingWinner, setPendingWinner] = useState<'a' | 'b' | 'draw' | null>(null)

  const match = data?.matches?.find((m) => m.id === matchId)
  if (!match) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <p className="text-fg-muted">{t('common.loading')}</p>
      </div>
    )
  }

  const version = match.version || 1

  const submitWinner = (winner: 'a' | 'b' | 'draw') => {
    setPendingWinner(winner)
    setConfirmOpen(true)
  }

  const confirmResult = () => {
    if (!pendingWinner) return
    const result = {
      winnerId:
        pendingWinner === 'a'
          ? match.participantA
          : pendingWinner === 'b'
            ? match.participantB
            : null,
      isDraw: pendingWinner === 'draw',
      isForfeit: false,
    }

    updateResult.mutate(
      { result, version },
      {
        onSuccess: () => {
          toast(t('match.resultRecorded'), 'success')
          navigate(`/tournaments/${id}`)
        },
        onError: (err: Error) => {
          if (err.message.includes('409')) {
            toast(t('match.conflictError'), 'error')
          }
        },
      },
    )
    setConfirmOpen(false)
  }

  const confirmForfeit = () => {
    forfeit.mutate(undefined, {
      onSuccess: () => {
        toast(t('match.resultRecorded'), 'success')
        navigate(`/tournaments/${id}`)
      },
    })
    setForfeitOpen(false)
  }

  const pa = match.participantA
  const pb = match.participantB

  return (
    <div className="max-w-sm mx-auto">
      <h1 className="font-heading text-xl text-fg mb-6 text-center">
        {t('tournament.round')} {match.round}, Match {match.slot + 1}
      </h1>

      {/* Player cards */}
      <div className="flex gap-4 mb-6">
        <Card padding="sm" className="flex-1 text-center">
          <p className="font-heading text-lg text-fg truncate">{pa || 'TBD'}</p>
        </Card>
        <div className="flex items-center text-fg-muted font-heading">vs</div>
        <Card padding="sm" className="flex-1 text-center">
          <p className="font-heading text-lg text-fg truncate">{pb || 'TBD'}</p>
        </Card>
      </div>

      {/* Winner model */}
      <div className="space-y-3">
        <Button
          variant="primary"
          size="lg"
          className="w-full min-h-[56px]"
          onClick={() => submitWinner('a')}
        >
          {pa} {t('match.playerAWins')}
        </Button>
        <Button
          variant="primary"
          size="lg"
          className="w-full min-h-[56px]"
          onClick={() => submitWinner('b')}
        >
          {pb} {t('match.playerBWins')}
        </Button>
        <Button
          variant="secondary"
          size="lg"
          className="w-full min-h-[56px]"
          onClick={() => submitWinner('draw')}
        >
          {t('match.draw')}
        </Button>
      </div>

      {/* Forfeit */}
      <div className="flex gap-2 mt-4">
        <Button
          variant="danger"
          size="sm"
          className="flex-1"
          onClick={() => setForfeitOpen('a')}
        >
          {pa} {t('match.forfeit')}
        </Button>
        <Button
          variant="danger"
          size="sm"
          className="flex-1"
          onClick={() => setForfeitOpen('b')}
        >
          {pb} {t('match.forfeit')}
        </Button>
      </div>

      <div className="mt-6">
        <Button
          variant="ghost"
          size="md"
          className="w-full"
          onClick={() => navigate(`/tournaments/${id}`)}
        >
          {t('common.cancel')}
        </Button>
      </div>

      {/* Confirm modal */}
      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title={t('match.confirmSubmit')}
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={() => setConfirmOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button variant="primary" size="sm" loading={updateResult.isPending} onClick={confirmResult}>
              {t('match.confirm')}
            </Button>
          </>
        }
      >
        <p className="text-fg-muted text-sm">
          {t('match.confirmSubmit')}
        </p>
      </Modal>

      {/* Forfeit modal */}
      <Modal
        open={!!forfeitOpen}
        onClose={() => setForfeitOpen(false)}
        title={t('match.forfeit')}
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={() => setForfeitOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={forfeit.isPending}
              onClick={() => forfeitOpen && confirmForfeit()}
            >
              {t('common.confirm')}
            </Button>
          </>
        }
      >
        <p className="text-fg-muted text-sm">
          {forfeitOpen === 'a' ? pa : pb} — {t('match.forfeitConfirm')}
        </p>
      </Modal>
    </div>
  )
}
