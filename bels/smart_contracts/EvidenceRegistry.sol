// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title  EvidenceRegistry
 * @notice Immutable registry that anchors fraud-evidence hashes and their chain of
 *         custody for the TGIE Blockchain Evidence Ledger System (BELS).
 *
 *         NO FILE CONTENT IS STORED ON-CHAIN — only the SHA-256 hash, identifiers,
 *         a metadata digest, the registrant's signature reference and custody events.
 *
 *         The Python BlockchainProvider interface (bels/blockchain_ledger/provider.py)
 *         mirrors this contract 1:1, so migrating BELS from the internal demo ledger to
 *         this contract on a bank-owned / RBI-approved EVM network is a configuration
 *         change rather than a redesign.
 */
contract EvidenceRegistry {
    enum Status { None, Registered, Verified, Tampered, Archived }

    struct CustodyEvent {
        string  action;      // UPLOAD | REVIEW | ACCESS | EXPORT | TRANSFER | SHARE | ARCHIVE | VERIFY
        address actor;
        string  detail;
        uint256 timestamp;
    }

    struct Evidence {
        bytes32 fileHash;        // SHA-256 of the evidence file
        bytes32 metadataHash;    // digest of the off-chain metadata manifest
        string  caseId;
        string  evidenceId;
        address owner;
        Status  status;
        uint256 timestamp;       // registration time
        uint256 verificationCount;
        bool    exists;
    }

    mapping(bytes32 => Evidence) private records;            // keccak(evidenceId) => Evidence
    mapping(bytes32 => CustodyEvent[]) private custody;      // keccak(evidenceId) => events
    bytes32[] private allKeys;

    event EvidenceRegistered(string evidenceId, string caseId, bytes32 fileHash, address owner, uint256 timestamp);
    event EvidenceVerified(string evidenceId, bool matched, address verifier, uint256 timestamp);
    event CustodyUpdated(string evidenceId, string action, address actor, uint256 timestamp);

    function _key(string memory evidenceId) private pure returns (bytes32) {
        return keccak256(abi.encodePacked(evidenceId));
    }

    /// @notice Register a new piece of evidence. Reverts if the ID already exists.
    function registerEvidence(
        string calldata evidenceId,
        string calldata caseId,
        bytes32 fileHash,
        bytes32 metadataHash
    ) external {
        bytes32 k = _key(evidenceId);
        require(!records[k].exists, "evidence already registered");
        records[k] = Evidence({
            fileHash: fileHash,
            metadataHash: metadataHash,
            caseId: caseId,
            evidenceId: evidenceId,
            owner: msg.sender,
            status: Status.Registered,
            timestamp: block.timestamp,
            verificationCount: 0,
            exists: true
        });
        allKeys.push(k);
        custody[k].push(CustodyEvent("REGISTER", msg.sender, "registered", block.timestamp));
        emit EvidenceRegistered(evidenceId, caseId, fileHash, msg.sender, block.timestamp);
    }

    /// @notice Verify a candidate hash against the anchored hash. Records the attempt.
    function verifyEvidence(string calldata evidenceId, bytes32 candidateHash)
        external
        returns (bool matched)
    {
        bytes32 k = _key(evidenceId);
        require(records[k].exists, "evidence not found");
        matched = (records[k].fileHash == candidateHash);
        records[k].verificationCount += 1;
        if (matched) {
            if (records[k].status == Status.Registered) records[k].status = Status.Verified;
        } else {
            records[k].status = Status.Tampered;
        }
        custody[k].push(CustodyEvent("VERIFY", msg.sender, matched ? "VERIFIED" : "TAMPERED", block.timestamp));
        emit EvidenceVerified(evidenceId, matched, msg.sender, block.timestamp);
    }

    /// @notice Append a chain-of-custody event.
    function updateCustody(string calldata evidenceId, string calldata action, string calldata detail) external {
        bytes32 k = _key(evidenceId);
        require(records[k].exists, "evidence not found");
        custody[k].push(CustodyEvent(action, msg.sender, detail, block.timestamp));
        if (keccak256(bytes(action)) == keccak256("ARCHIVE")) records[k].status = Status.Archived;
        emit CustodyUpdated(evidenceId, action, msg.sender, block.timestamp);
    }

    /// @notice Read the full evidence record.
    function getEvidenceRecord(string calldata evidenceId)
        external
        view
        returns (
            bytes32 fileHash,
            bytes32 metadataHash,
            string memory caseId,
            address owner,
            Status status,
            uint256 timestamp,
            uint256 verificationCount,
            uint256 custodyEventCount
        )
    {
        bytes32 k = _key(evidenceId);
        require(records[k].exists, "evidence not found");
        Evidence storage e = records[k];
        return (e.fileHash, e.metadataHash, e.caseId, e.owner, e.status,
                e.timestamp, e.verificationCount, custody[k].length);
    }

    /// @notice Read the ordered chain-of-custody / audit trail.
    function getAuditTrail(string calldata evidenceId) external view returns (CustodyEvent[] memory) {
        return custody[_key(evidenceId)];
    }

    function totalEvidence() external view returns (uint256) {
        return allKeys.length;
    }
}
