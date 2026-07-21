using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TourneyHub.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddMatches : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "matches",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    TournamentId = table.Column<Guid>(type: "uuid", nullable: false),
                    RoundNumber = table.Column<int>(type: "integer", nullable: false),
                    PositionInRound = table.Column<int>(type: "integer", nullable: false),
                    ParticipantAId = table.Column<Guid>(type: "uuid", nullable: true),
                    ParticipantBId = table.Column<Guid>(type: "uuid", nullable: true),
                    WinnerId = table.Column<Guid>(type: "uuid", nullable: true),
                    State = table.Column<string>(type: "text", nullable: false),
                    IsByeMatch = table.Column<bool>(type: "boolean", nullable: false),
                    AdvanceToMatchId = table.Column<Guid>(type: "uuid", nullable: true),
                    Version = table.Column<int>(type: "integer", nullable: false),
                    OrganizationId = table.Column<Guid>(type: "uuid", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_matches", x => x.Id);
                    table.ForeignKey(
                        name: "FK_matches_matches_AdvanceToMatchId",
                        column: x => x.AdvanceToMatchId,
                        principalTable: "matches",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_matches_organizations_OrganizationId",
                        column: x => x.OrganizationId,
                        principalTable: "organizations",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_matches_participants_ParticipantAId",
                        column: x => x.ParticipantAId,
                        principalTable: "participants",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_matches_participants_ParticipantBId",
                        column: x => x.ParticipantBId,
                        principalTable: "participants",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_matches_tournaments_TournamentId",
                        column: x => x.TournamentId,
                        principalTable: "tournaments",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_matches_AdvanceToMatchId",
                table: "matches",
                column: "AdvanceToMatchId");

            migrationBuilder.CreateIndex(
                name: "IX_matches_OrganizationId_Id",
                table: "matches",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_matches_ParticipantAId",
                table: "matches",
                column: "ParticipantAId");

            migrationBuilder.CreateIndex(
                name: "IX_matches_ParticipantBId",
                table: "matches",
                column: "ParticipantBId");

            migrationBuilder.CreateIndex(
                name: "IX_matches_TournamentId_RoundNumber_PositionInRound",
                table: "matches",
                columns: new[] { "TournamentId", "RoundNumber", "PositionInRound" },
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "matches");
        }
    }
}
