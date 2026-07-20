using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TourneyHub.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddLeaguesAndSeasons : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AlterColumn<string>(
                name: "Name",
                table: "leagues",
                type: "character varying(256)",
                maxLength: 256,
                nullable: false,
                oldClrType: typeof(string),
                oldType: "text");

            migrationBuilder.AddColumn<string>(
                name: "Description",
                table: "leagues",
                type: "character varying(2000)",
                maxLength: 2000,
                nullable: true);

            migrationBuilder.AddColumn<Guid>(
                name: "OwnerId",
                table: "leagues",
                type: "uuid",
                nullable: false,
                defaultValue: new Guid("00000000-0000-0000-0000-000000000000"));

            migrationBuilder.AddColumn<string>(
                name: "Slug",
                table: "leagues",
                type: "character varying(128)",
                maxLength: 128,
                nullable: false,
                defaultValue: "");

            migrationBuilder.AddColumn<string>(
                name: "State",
                table: "leagues",
                type: "text",
                nullable: false,
                defaultValue: "");

            migrationBuilder.AddColumn<string>(
                name: "Visibility",
                table: "leagues",
                type: "text",
                nullable: false,
                defaultValue: "");

            migrationBuilder.CreateTable(
                name: "seasons",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    LeagueId = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: false),
                    State = table.Column<string>(type: "text", nullable: false),
                    StartedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CompletedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    RngSeed = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    Version = table.Column<int>(type: "integer", nullable: false),
                    OrganizationId = table.Column<Guid>(type: "uuid", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_seasons", x => x.Id);
                    table.ForeignKey(
                        name: "FK_seasons_leagues_LeagueId",
                        column: x => x.LeagueId,
                        principalTable: "leagues",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_seasons_organizations_OrganizationId",
                        column: x => x.OrganizationId,
                        principalTable: "organizations",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_leagues_OrganizationId_Slug",
                table: "leagues",
                columns: new[] { "OrganizationId", "Slug" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_seasons_LeagueId_State",
                table: "seasons",
                columns: new[] { "LeagueId", "State" },
                filter: "\"State\" = 'Active'");

            migrationBuilder.CreateIndex(
                name: "IX_seasons_OrganizationId_Id",
                table: "seasons",
                columns: new[] { "OrganizationId", "Id" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "seasons");

            migrationBuilder.DropIndex(
                name: "IX_leagues_OrganizationId_Slug",
                table: "leagues");

            migrationBuilder.DropColumn(
                name: "Description",
                table: "leagues");

            migrationBuilder.DropColumn(
                name: "OwnerId",
                table: "leagues");

            migrationBuilder.DropColumn(
                name: "Slug",
                table: "leagues");

            migrationBuilder.DropColumn(
                name: "State",
                table: "leagues");

            migrationBuilder.DropColumn(
                name: "Visibility",
                table: "leagues");

            migrationBuilder.AlterColumn<string>(
                name: "Name",
                table: "leagues",
                type: "text",
                nullable: false,
                oldClrType: typeof(string),
                oldType: "character varying(256)",
                oldMaxLength: 256);
        }
    }
}
